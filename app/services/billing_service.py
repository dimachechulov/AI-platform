from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

import stripe
from fastapi import HTTPException

from app.core.config import settings
from app.db.database import DatabaseSession
from app.db.billing_repository import BillingRepository

MONEY_Q = Decimal("0.0001")

MODEL_PRICING_PER_MILLION: dict[str, dict[str, Decimal]] = {
    # https://ai.google.dev/gemini-api/docs/pricing
    "gemini-2.5-flash": {"input": Decimal("0.30"), "output": Decimal("2.50")},
    "gemini-2.5-pro": {"input": Decimal("1.25"), "output": Decimal("10.00")},
}


@dataclass(frozen=True)
class PlanLimits:
    max_documents: Optional[int]
    allowed_models: Optional[set[str]]
    max_bots: Optional[int]
    max_messages: Optional[int]


PLAN_LIMITS: dict[str, PlanLimits] = {
    "trial": PlanLimits(
        max_documents=3,
        allowed_models={"gemini-2.5-flash"},
        max_bots=1,
        max_messages=100,
    ),
    "lite": PlanLimits(
        max_documents=10,
        allowed_models={"gemini-2.5-flash", "gemini-2.5-pro"},
        max_bots=3,
        max_messages=None,
    ),
    "full": PlanLimits(
        max_documents=None,
        allowed_models=None,
        max_bots=None,
        max_messages=None,
    ),
}


def normalize_model_name(model: Optional[str]) -> str:
    if not model:
        return "gemini-2.5-flash"
    value = model.strip().lower()
    if value.startswith("models/"):
        value = value.split("/", 1)[1]
    return value


def get_plan_limits(plan: str) -> PlanLimits:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["trial"])


def calculate_llm_cost_usd(
    *,
    model_name: Optional[str],
    input_tokens: int,
    output_tokens: int,
) -> Decimal:
    normalized = normalize_model_name(model_name)
    pricing = MODEL_PRICING_PER_MILLION.get(normalized)
    if not pricing:
        return Decimal("0.0000")
    input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * pricing["input"]
    output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * pricing["output"]
    return (input_cost + output_cost).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def is_workspace_subscription_active(billing: dict) -> bool:
    plan = billing.get("plan", "trial")
    status = (billing.get("subscription_status") or "").lower()
    if plan == "trial":
        trial_ends = billing.get("trial_ends_at")
        if not trial_ends:
            return True
        if trial_ends.tzinfo is None:
            trial_ends = trial_ends.replace(tzinfo=timezone.utc)
        return trial_ends > datetime.now(timezone.utc)
    return status in {"active", "trialing"}


def trial_end_datetime() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=settings.TRIAL_DAYS)


class BillingService:
    def __init__(self, repository: BillingRepository):
        self.repository = repository

    def _init_stripe(self) -> None:
        if stripe is None:
            raise HTTPException(status_code=500, detail="Stripe package not installed")
        if not settings.STRIPE_SECRET_KEY:
            raise HTTPException(status_code=500, detail="STRIPE_SECRET_KEY is not configured")
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def _get_plan_price_id(self, plan: str) -> str:
        if plan == "lite" and settings.STRIPE_PRICE_LITE_ID:
            return settings.STRIPE_PRICE_LITE_ID
        if plan == "full" and settings.STRIPE_PRICE_FULL_ID:
            return settings.STRIPE_PRICE_FULL_ID
        raise HTTPException(status_code=500, detail=f"Stripe price id for '{plan}' is not configured")

    @staticmethod
    def _align_bucket_start(dt: datetime, bucket_minutes: int) -> datetime:
        dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
        return dt.replace(minute=(dt.minute // bucket_minutes) * bucket_minutes)

    def _fill_spending_buckets(
        self,
        time_from: datetime,
        time_to: datetime,
        bucket_minutes: int,
        rows: List[dict],
    ) -> List[dict]:
        row_by_start = {self._align_bucket_start(r["bucket_start"], bucket_minutes): r for r in rows}
        out: list[dict] = []
        cur = self._align_bucket_start(time_from, bucket_minutes)
        delta = timedelta(minutes=bucket_minutes)
        while cur < time_to:
            nxt = cur + delta
            row = row_by_start.get(cur)
            out.append(
                {
                    "bucket_start": cur,
                    "bucket_end": nxt,
                    "spent_usd": (row["spent_usd"] if row else Decimal("0")).quantize(MONEY_Q),
                }
            )
            cur = nxt
        return out

    def get_or_create_billing_summary(self, db: DatabaseSession, workspace_id: int) -> dict:
        return self.repository.get_workspace_billing(db, workspace_id=workspace_id) or self.repository.ensure_workspace_billing(
            db, workspace_id=workspace_id
        )

    def get_plan_limits_info(self, db: DatabaseSession, workspace_id: int) -> dict:
        billing = self.get_or_create_billing_summary(db, workspace_id)
        plan_limits = get_plan_limits(billing["plan"])
        docs_count = self.repository.count_documents_for_workspace(db, workspace_id=workspace_id)
        bots_count = self.repository.count_bots_for_workspace(db, workspace_id=workspace_id)
        messages_count = self.repository.count_messages_for_workspace(db, workspace_id=workspace_id)
        subscription_active = is_workspace_subscription_active(billing)

        reason: Optional[str] = None
        if not subscription_active:
            reason = "Подписка неактивна. Продлите оплату."
        elif Decimal(billing["balance_usd"]) <= Decimal("0"):
            reason = "Недостаточно средств на балансе. Пополните баланс."

        can_upload_documents = subscription_active and (
            plan_limits.max_documents is None or docs_count < plan_limits.max_documents
        )
        can_create_bots = subscription_active and (plan_limits.max_bots is None or bots_count < plan_limits.max_bots)
        can_send_messages = subscription_active and Decimal(billing["balance_usd"]) > Decimal("0") and (
            plan_limits.max_messages is None or messages_count < plan_limits.max_messages
        )
        return {
            "workspace_id": workspace_id,
            "plan": billing["plan"],
            "subscription_active": subscription_active,
            "subscription_status": billing["subscription_status"],
            "balance_usd": Decimal(billing["balance_usd"]),
            "can_send_messages": can_send_messages,
            "can_upload_documents": can_upload_documents,
            "can_create_bots": can_create_bots,
            "limits": {
                "max_documents": plan_limits.max_documents,
                "max_bots": plan_limits.max_bots,
                "max_messages": plan_limits.max_messages,
                "allowed_models": sorted(list(plan_limits.allowed_models)) if plan_limits.allowed_models else [],
            },
            "usage": {"documents": docs_count, "bots": bots_count, "messages": messages_count},
            "reason": reason,
        }

    def get_spending(
        self,
        db: DatabaseSession,
        workspace_id: int,
        time_from: Optional[datetime],
        time_to: Optional[datetime],
        bucket_minutes: int,
    ) -> dict:
        now = datetime.now(timezone.utc)
        t_to = time_to.astimezone(timezone.utc) if time_to else now
        t_from = time_from.astimezone(timezone.utc) if time_from else t_to - timedelta(days=7)
        if t_from >= t_to:
            raise HTTPException(status_code=400, detail="time_from must be before time_to")
        totals = self.repository.get_spending_totals(db, workspace_id=workspace_id, time_from=t_from, time_to=t_to)
        buckets_raw = self.repository.get_spending_buckets(
            db,
            workspace_id=workspace_id,
            time_from=t_from,
            time_to=t_to,
            bucket_minutes=bucket_minutes,
        )
        buckets = self._fill_spending_buckets(t_from, t_to, bucket_minutes, buckets_raw)
        return {
            "workspace_id": workspace_id,
            "time_from": t_from,
            "time_to": t_to,
            "bucket_minutes": bucket_minutes,
            "spent_total_usd": totals["spent_usd"],
            "topped_up_total_usd": totals["topped_up_usd"],
            "buckets": buckets,
        }

    def create_subscription_checkout(
        self,
        db: DatabaseSession,
        workspace_id: int,
        plan: str,
        user_email: str,
    ) -> str:
        self._init_stripe()
        price_id = self._get_plan_price_id(plan)
        billing = self.get_or_create_billing_summary(db, workspace_id)
        customer_id = billing.get("stripe_customer_id")
        if not customer_id:
            customer = stripe.Customer.create(email=user_email, metadata={"workspace_id": workspace_id})
            customer_id = customer["id"]
            self.repository.update_workspace_billing(db, workspace_id=workspace_id, updates={"stripe_customer_id": customer_id})
            db.commit()
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{settings.FRONTEND_BASE_URL}/app/billing?checkout=success",
            cancel_url=f"{settings.FRONTEND_BASE_URL}/app/billing?checkout=cancel",
            metadata={"workspace_id": str(workspace_id), "plan": plan},
        )
        return session["url"]

    def create_topup_checkout(
        self,
        db: DatabaseSession,
        workspace_id: int,
        amount_usd: Decimal,
        user_email: str,
    ) -> str:
        self._init_stripe()
        amount_cents = int((amount_usd * 100).quantize(Decimal("1")))
        billing = self.get_or_create_billing_summary(db, workspace_id)
        customer_id = billing.get("stripe_customer_id")
        if not customer_id:
            customer = stripe.Customer.create(email=user_email, metadata={"workspace_id": workspace_id})
            customer_id = customer["id"]
            self.repository.update_workspace_billing(db, workspace_id=workspace_id, updates={"stripe_customer_id": customer_id})
            db.commit()
        session = stripe.checkout.Session.create(
            mode="payment",
            customer=customer_id,
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": "Workspace balance top-up"},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{settings.FRONTEND_BASE_URL}/app/billing?topup=success",
            cancel_url=f"{settings.FRONTEND_BASE_URL}/app/billing?topup=cancel",
            metadata={"workspace_id": str(workspace_id), "type": "topup", "amount_usd": str(amount_usd)},
        )
        return session["url"]

    def create_billing_portal(self, db: DatabaseSession, workspace_id: int) -> str:
        self._init_stripe()
        billing = self.repository.get_workspace_billing(db, workspace_id=workspace_id)
        if not billing or not billing.get("stripe_customer_id"):
            raise HTTPException(status_code=400, detail="No Stripe customer for workspace")
        session = stripe.billing_portal.Session.create(
            customer=billing["stripe_customer_id"],
            return_url=settings.BILLING_PORTAL_RETURN_URL,
        )
        return session["url"]

    def switch_to_trial_plan(self, db: DatabaseSession, workspace_id: int) -> dict:
        self._init_stripe()
        billing = self.get_or_create_billing_summary(db, workspace_id)
        subscription_id = billing.get("stripe_subscription_id")
        if subscription_id:
            stripe.Subscription.cancel(subscription_id)
        updated = self.repository.update_workspace_billing(
            db,
            workspace_id=workspace_id,
            updates={
                "plan": "trial",
                "subscription_status": "trialing",
                "stripe_subscription_id": None,
                "stripe_price_id": None,
                "trial_ends_at": trial_end_datetime(),
            },
        )
        db.commit()
        return updated

    def handle_stripe_webhook(self, db: DatabaseSession, payload: bytes, stripe_signature: Optional[str]) -> Dict[str, bool]:
        self._init_stripe()
        if not settings.STRIPE_WEBHOOK_SECRET:
            raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET is not configured")
        if not stripe_signature:
            raise HTTPException(status_code=400, detail="Missing Stripe signature header")
        event = stripe.Webhook.construct_event(payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
        event_id = event.id
        event_type = event.type
        data = event.data.object

        if event_id and self.repository.has_billing_transaction_for_stripe_event(db, stripe_event_id=event_id):
            return {"received": True, "duplicate": True}

        if event_type == "checkout.session.completed":
            metadata = data.metadata
            workspace_id = int(metadata["workspace_id"])
            if workspace_id:
                mode = data.mode
                if mode == "subscription":
                    subscription_id = data.subscription
                    customer_id = data.customer
                    resolved_plan = metadata["plan"]
                    price_id = None
                    if subscription_id:
                        subscription_obj = stripe.Subscription.retrieve(subscription_id)
                        items_data = subscription_obj.items.data
                        first_item = items_data[0] if items_data else None
                        price = first_item.price if first_item else None
                        price_id = price.id if price else None
                        if price_id == settings.STRIPE_PRICE_LITE_ID:
                            resolved_plan = "lite"
                        elif price_id == settings.STRIPE_PRICE_FULL_ID:
                            resolved_plan = "full"
                    self.repository.update_workspace_billing(
                        db,
                        workspace_id=workspace_id,
                        updates={
                            "plan": resolved_plan,
                            "subscription_status": "active",
                            "stripe_customer_id": customer_id,
                            "stripe_subscription_id": subscription_id,
                            "stripe_price_id": price_id,
                        },
                    )
                elif mode == "payment" and metadata["type"] == "topup":
                    amount_total = data.amount_total
                    amount = Decimal(str((amount_total or 0) / 100)).quantize(MONEY_Q)
                    self.repository.adjust_workspace_balance(db, workspace_id=workspace_id, amount_delta=amount)
                    self.repository.create_billing_transaction(
                        db,
                        workspace_id=workspace_id,
                        transaction_type="topup",
                        amount_usd=amount,
                        description="Stripe top-up payment",
                        stripe_event_id=event_id,
                        metadata_json={"checkout_session_id": data.id},
                    )
        elif event_type == "invoice.paid":
            customer_id = data.customer
            billing = self.repository.get_workspace_billing_by_customer_id(db, stripe_customer_id=customer_id) if customer_id else None
            if billing:
                amount_paid = data.amount_paid
                amount = Decimal(str((amount_paid or 0) / 100)).quantize(MONEY_Q)
                resolved_plan = billing["plan"]
                price_id = billing.get("stripe_price_id")
                subscription_id = billing.get("stripe_subscription_id")
                if subscription_id:
                    subscription_obj = stripe.Subscription.retrieve(subscription_id)
                    items_data = subscription_obj.items.data
                    first_item = items_data[0] if items_data else None
                    price = first_item.price if first_item else None
                    price_id = (price.id if price else None) or price_id
                    if price_id == settings.STRIPE_PRICE_LITE_ID:
                        resolved_plan = "lite"
                    elif price_id == settings.STRIPE_PRICE_FULL_ID:
                        resolved_plan = "full"
                self.repository.update_workspace_billing(
                    db,
                    workspace_id=billing["workspace_id"],
                    updates={
                        "plan": resolved_plan,
                        "subscription_status": "active",
                        "stripe_subscription_id": subscription_id,
                        "stripe_price_id": price_id,
                    },
                )
                self.repository.create_billing_transaction(
                    db,
                    workspace_id=billing["workspace_id"],
                    transaction_type="subscription_payment",
                    amount_usd=amount,
                    description=f"Subscription payment ({resolved_plan})",
                    stripe_event_id=event_id,
                    metadata_json={"invoice_id": data.id},
                )
        elif event_type in {"invoice.payment_failed", "customer.subscription.deleted"}:
            customer_id = data.customer
            billing = self.repository.get_workspace_billing_by_customer_id(db, stripe_customer_id=customer_id) if customer_id else None
            if billing:
                self.repository.update_workspace_billing(
                    db,
                    workspace_id=billing["workspace_id"],
                    updates={"subscription_status": "past_due"},
                )
        elif event_type == "customer.subscription.updated":
            sub_id = data.id
            billing = self.repository.get_workspace_billing_by_subscription_id(db, stripe_subscription_id=sub_id) if sub_id else None
            if billing:
                items_data = data.items.data
                first_item = items_data[0] if items_data else None
                price = first_item.price if first_item else None
                price_id = price.id if price else None
                plan = billing["plan"]
                if price_id == settings.STRIPE_PRICE_LITE_ID:
                    plan = "lite"
                elif price_id == settings.STRIPE_PRICE_FULL_ID:
                    plan = "full"
                self.repository.update_workspace_billing(
                    db,
                    workspace_id=billing["workspace_id"],
                    updates={
                        "plan": plan,
                        "subscription_status": data.status or billing["subscription_status"],
                        "stripe_price_id": price_id,
                    },
                )
        db.commit()
        return {"received": True}
