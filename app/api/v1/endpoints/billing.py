from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, get_user_workspace
from app.api.dependencies import check_workspace_access
from app.core.config import settings
from app.db import repositories as repo
from app.db.database import DatabaseSession, get_db
from app.services.billing_service import MONEY_Q
from app.services.billing_service import get_plan_limits, is_workspace_subscription_active, trial_end_datetime
import stripe


router = APIRouter()


class BillingSummaryResponse(BaseModel):
    workspace_id: int
    plan: str
    subscription_status: str
    balance_usd: Decimal
    current_period_end: Optional[datetime]
    trial_ends_at: Optional[datetime]


class BillingTransactionResponse(BaseModel):
    id: int
    transaction_type: str
    amount_usd: Decimal
    description: Optional[str] = None
    created_at: datetime
    metadata_json: Optional[dict] = None


class SpendingBucket(BaseModel):
    bucket_start: datetime
    bucket_end: datetime
    spent_usd: Decimal


class SpendingResponse(BaseModel):
    workspace_id: int
    time_from: datetime
    time_to: datetime
    bucket_minutes: int
    spent_total_usd: Decimal
    topped_up_total_usd: Decimal
    buckets: List[SpendingBucket]


class CheckoutRequest(BaseModel):
    workspace_id: int
    plan: str = Field(pattern="^(lite|full)$")


class TopUpRequest(BaseModel):
    workspace_id: int
    amount_usd: Decimal = Field(gt=Decimal("0"), le=Decimal("500"))


class CheckoutResponse(BaseModel):
    url: str


class PlanLimitsResponse(BaseModel):
    workspace_id: int
    plan: str
    subscription_active: bool
    subscription_status: str
    balance_usd: Decimal
    can_send_messages: bool
    can_upload_documents: bool
    can_create_bots: bool
    limits: dict
    usage: dict
    reason: Optional[str] = None


def _init_stripe() -> None:
    if stripe is None:
        raise HTTPException(status_code=500, detail="Stripe package not installed")
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="STRIPE_SECRET_KEY is not configured")
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _get_plan_price_id(plan: str) -> str:
    if plan == "lite" and settings.STRIPE_PRICE_LITE_ID:
        return settings.STRIPE_PRICE_LITE_ID
    if plan == "full" and settings.STRIPE_PRICE_FULL_ID:
        return settings.STRIPE_PRICE_FULL_ID
    raise HTTPException(status_code=500, detail=f"Stripe price id for '{plan}' is not configured")


def _align_bucket_start(dt: datetime, bucket_minutes: int) -> datetime:
    dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return dt.replace(minute=(dt.minute // bucket_minutes) * bucket_minutes)


def _fill_spending_buckets(time_from: datetime, time_to: datetime, bucket_minutes: int, rows: List[dict]) -> List[dict]:
    row_by_start = {_align_bucket_start(r["bucket_start"], bucket_minutes): r for r in rows}
    out: list[dict] = []
    cur = _align_bucket_start(time_from, bucket_minutes)
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


@router.get("/summary", response_model=BillingSummaryResponse)
async def get_billing_summary(
    workspace_id: int = Query(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(workspace_id, current_user, db)
    billing = repo.get_workspace_billing(db, workspace_id=workspace_id) or repo.ensure_workspace_billing(
        db, workspace_id=workspace_id
    )
    db.commit()
    return BillingSummaryResponse(**billing)


@router.get("/limits", response_model=PlanLimitsResponse)
async def get_plan_limits_for_workspace(
    workspace_id: int = Query(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await check_workspace_access(workspace_id, current_user, db)
    billing = repo.get_workspace_billing(db, workspace_id=workspace_id) or repo.ensure_workspace_billing(
        db, workspace_id=workspace_id
    )
    plan_limits = get_plan_limits(billing["plan"])
    docs_count = repo.count_documents_for_workspace(db, workspace_id=workspace_id)
    bots_count = repo.count_bots_for_workspace(db, workspace_id=workspace_id)
    messages_count = repo.count_messages_for_workspace(db, workspace_id=workspace_id)
    subscription_active = is_workspace_subscription_active(billing)
    reason: Optional[str] = None
    if not subscription_active:
        reason = "Подписка неактивна. Продлите оплату."
    elif Decimal(billing["balance_usd"]) <= Decimal("0"):
        reason = "Недостаточно средств на балансе. Пополните баланс."

    can_upload_documents = subscription_active and (
        plan_limits.max_documents is None or docs_count < plan_limits.max_documents
    )
    can_create_bots = subscription_active and (
        plan_limits.max_bots is None or bots_count < plan_limits.max_bots
    )
    can_send_messages = subscription_active and Decimal(billing["balance_usd"]) > Decimal("0") and (
        plan_limits.max_messages is None or messages_count < plan_limits.max_messages
    )
    return PlanLimitsResponse(
        workspace_id=workspace_id,
        plan=billing["plan"],
        subscription_active=subscription_active,
        subscription_status=billing["subscription_status"],
        balance_usd=Decimal(billing["balance_usd"]),
        can_send_messages=can_send_messages,
        can_upload_documents=can_upload_documents,
        can_create_bots=can_create_bots,
        limits={
            "max_documents": plan_limits.max_documents,
            "max_bots": plan_limits.max_bots,
            "max_messages": plan_limits.max_messages,
            "allowed_models": sorted(list(plan_limits.allowed_models)) if plan_limits.allowed_models else [],
        },
        usage={
            "documents": docs_count,
            "bots": bots_count,
            "messages": messages_count,
        },
        reason=reason,
    )


@router.get("/transactions", response_model=List[BillingTransactionResponse])
async def get_billing_transactions(
    workspace_id: int = Query(...),
    limit: int = Query(100, ge=1, le=500),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(workspace_id, current_user, db)
    return [BillingTransactionResponse(**r) for r in repo.list_billing_transactions(db, workspace_id=workspace_id, limit=limit)]


@router.get("/spending", response_model=SpendingResponse)
async def get_spending_usage(
    workspace_id: int = Query(...),
    time_from: Optional[datetime] = Query(None),
    time_to: Optional[datetime] = Query(None),
    bucket_minutes: int = Query(60, ge=5, le=24 * 60),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(workspace_id, current_user, db)
    now = datetime.now(timezone.utc)
    t_to = time_to.astimezone(timezone.utc) if time_to else now
    t_from = time_from.astimezone(timezone.utc) if time_from else t_to - timedelta(days=7)
    if t_from >= t_to:
        raise HTTPException(status_code=400, detail="time_from must be before time_to")
    totals = repo.get_spending_totals(db, workspace_id=workspace_id, time_from=t_from, time_to=t_to)
    buckets_raw = repo.get_spending_buckets(
        db,
        workspace_id=workspace_id,
        time_from=t_from,
        time_to=t_to,
        bucket_minutes=bucket_minutes,
    )
    buckets = _fill_spending_buckets(t_from, t_to, bucket_minutes, buckets_raw)
    return SpendingResponse(
        workspace_id=workspace_id,
        time_from=t_from,
        time_to=t_to,
        bucket_minutes=bucket_minutes,
        spent_total_usd=totals["spent_usd"],
        topped_up_total_usd=totals["topped_up_usd"],
        buckets=[SpendingBucket(**b) for b in buckets],
    )


@router.post("/checkout/subscription", response_model=CheckoutResponse)
async def create_subscription_checkout(
    payload: CheckoutRequest,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(payload.workspace_id, current_user, db)
    _init_stripe()
    price_id = _get_plan_price_id(payload.plan)
    billing = repo.get_workspace_billing(db, workspace_id=payload.workspace_id) or repo.ensure_workspace_billing(
        db, workspace_id=payload.workspace_id
    )
    customer_id = billing.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(email=current_user["email"], metadata={"workspace_id": payload.workspace_id})
        customer_id = customer["id"]
        repo.update_workspace_billing(db, workspace_id=payload.workspace_id, updates={"stripe_customer_id": customer_id})
        db.commit()

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.FRONTEND_BASE_URL}/app/billing?checkout=success",
        cancel_url=f"{settings.FRONTEND_BASE_URL}/app/billing?checkout=cancel",
        metadata={"workspace_id": str(payload.workspace_id), "plan": payload.plan},
    )
    return CheckoutResponse(url=session["url"])


@router.post("/checkout/topup", response_model=CheckoutResponse)
async def create_topup_checkout(
    payload: TopUpRequest,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(payload.workspace_id, current_user, db)
    _init_stripe()
    amount_cents = int((payload.amount_usd * 100).quantize(Decimal("1")))
    billing = repo.get_workspace_billing(db, workspace_id=payload.workspace_id) or repo.ensure_workspace_billing(
        db, workspace_id=payload.workspace_id
    )
    customer_id = billing.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(email=current_user["email"], metadata={"workspace_id": payload.workspace_id})
        customer_id = customer["id"]
        repo.update_workspace_billing(db, workspace_id=payload.workspace_id, updates={"stripe_customer_id": customer_id})
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
        metadata={"workspace_id": str(payload.workspace_id), "type": "topup", "amount_usd": str(payload.amount_usd)},
    )
    return CheckoutResponse(url=session["url"])


@router.post("/portal", response_model=CheckoutResponse)
async def create_billing_portal(
    workspace_id: int = Query(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(workspace_id, current_user, db)
    _init_stripe()
    billing = repo.get_workspace_billing(db, workspace_id=workspace_id)
    if not billing or not billing.get("stripe_customer_id"):
        raise HTTPException(status_code=400, detail="No Stripe customer for workspace")
    session = stripe.billing_portal.Session.create(
        customer=billing["stripe_customer_id"],
        return_url=settings.BILLING_PORTAL_RETURN_URL,
    )
    return CheckoutResponse(url=session["url"])


@router.post("/plan/trial", response_model=BillingSummaryResponse)
async def switch_to_trial_plan(
    workspace_id: int = Query(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(workspace_id, current_user, db)
    _init_stripe()
    billing = repo.get_workspace_billing(db, workspace_id=workspace_id) or repo.ensure_workspace_billing(
        db, workspace_id=workspace_id
    )
    subscription_id = billing.get("stripe_subscription_id")
    if subscription_id:
        stripe.Subscription.cancel(subscription_id)
    updated = repo.update_workspace_billing(
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
    return BillingSummaryResponse(**updated)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: DatabaseSession = Depends(get_db),
):
    _init_stripe()
    payload = await request.body()
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET is not configured")
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")
    event = stripe.Webhook.construct_event(payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
    event_id = event.id
    event_type = event.type
    data = event.data.object

    if event_id and repo.has_billing_transaction_for_stripe_event(db, stripe_event_id=event_id):
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
                repo.update_workspace_billing(
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
                repo.adjust_workspace_balance(db, workspace_id=workspace_id, amount_delta=amount)
                repo.create_billing_transaction(
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
        billing = repo.get_workspace_billing_by_customer_id(db, stripe_customer_id=customer_id) if customer_id else None
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
            repo.update_workspace_billing(
                db,
                workspace_id=billing["workspace_id"],
                updates={
                    "plan": resolved_plan,
                    "subscription_status": "active",
                    "stripe_subscription_id": subscription_id,
                    "stripe_price_id": price_id,
                },
            )
            repo.create_billing_transaction(
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
        billing = repo.get_workspace_billing_by_customer_id(db, stripe_customer_id=customer_id) if customer_id else None
        if billing:
            repo.update_workspace_billing(
                db,
                workspace_id=billing["workspace_id"],
                updates={"subscription_status": "past_due"},
            )
    elif event_type == "customer.subscription.updated":
        sub_id = data.id
        billing = repo.get_workspace_billing_by_subscription_id(db, stripe_subscription_id=sub_id) if sub_id else None
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
            repo.update_workspace_billing(
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
