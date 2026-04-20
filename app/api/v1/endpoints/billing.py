from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, get_user_workspace
from app.api.dependencies import check_workspace_access
from app.db.billing_repository import BillingRepository
from app.db.database import DatabaseSession, get_db
from app.services.billing_service import BillingService


router = APIRouter()
billing_service = BillingService(BillingRepository())


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


@router.get("/summary", response_model=BillingSummaryResponse)
async def get_billing_summary(
    workspace_id: int = Query(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(workspace_id, current_user, db)
    billing = billing_service.get_or_create_billing_summary(db, workspace_id)
    db.commit()
    return BillingSummaryResponse(**billing)


@router.get("/limits", response_model=PlanLimitsResponse)
async def get_plan_limits_for_workspace(
    workspace_id: int = Query(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await check_workspace_access(workspace_id, current_user, db)
    return PlanLimitsResponse(**billing_service.get_plan_limits_info(db, workspace_id))


@router.get("/transactions", response_model=List[BillingTransactionResponse])
async def get_billing_transactions(
    workspace_id: int = Query(...),
    limit: int = Query(100, ge=1, le=500),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(workspace_id, current_user, db)
    rows = billing_service.repository.list_billing_transactions(db, workspace_id=workspace_id, limit=limit)
    return [BillingTransactionResponse(**r) for r in rows]


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
    spending = billing_service.get_spending(db, workspace_id, time_from, time_to, bucket_minutes)
    return SpendingResponse(
        workspace_id=spending["workspace_id"],
        time_from=spending["time_from"],
        time_to=spending["time_to"],
        bucket_minutes=spending["bucket_minutes"],
        spent_total_usd=spending["spent_total_usd"],
        topped_up_total_usd=spending["topped_up_total_usd"],
        buckets=[SpendingBucket(**b) for b in spending["buckets"]],
    )


@router.post("/checkout/subscription", response_model=CheckoutResponse)
async def create_subscription_checkout(
    payload: CheckoutRequest,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(payload.workspace_id, current_user, db)
    url = billing_service.create_subscription_checkout(
        db, payload.workspace_id, payload.plan, current_user["email"]
    )
    return CheckoutResponse(url=url)


@router.post("/checkout/topup", response_model=CheckoutResponse)
async def create_topup_checkout(
    payload: TopUpRequest,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(payload.workspace_id, current_user, db)
    url = billing_service.create_topup_checkout(
        db, payload.workspace_id, payload.amount_usd, current_user["email"]
    )
    return CheckoutResponse(url=url)


@router.post("/portal", response_model=CheckoutResponse)
async def create_billing_portal(
    workspace_id: int = Query(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(workspace_id, current_user, db)
    url = billing_service.create_billing_portal(db, workspace_id)
    return CheckoutResponse(url=url)


@router.post("/plan/trial", response_model=BillingSummaryResponse)
async def switch_to_trial_plan(
    workspace_id: int = Query(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await get_user_workspace(workspace_id, current_user, db)
    updated = billing_service.switch_to_trial_plan(db, workspace_id)
    return BillingSummaryResponse(**updated)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: DatabaseSession = Depends(get_db),
):
    payload = await request.body()
    return billing_service.handle_stripe_webhook(db, payload, stripe_signature)
