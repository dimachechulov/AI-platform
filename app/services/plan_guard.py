from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db import repositories as repo
from app.services.billing_service import get_plan_limits, is_workspace_subscription_active, normalize_model_name


def _ensure_billing(db: Session, workspace_id: int) -> dict:
    billing = repo.get_workspace_billing(db, workspace_id=workspace_id)
    if not billing:
        billing = repo.ensure_workspace_billing(db, workspace_id=workspace_id)
    return billing


def enforce_subscription_active(db: Session, workspace_id: int) -> dict:
    billing = _ensure_billing(db, workspace_id)
    if not is_workspace_subscription_active(billing):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription inactive. Renew payment to continue.",
        )
    return billing


def enforce_document_limit(db: Session, workspace_id: int) -> None:
    billing = enforce_subscription_active(db, workspace_id)
    limit = get_plan_limits(billing["plan"]).max_documents
    if limit is None:
        return
    current = repo.count_documents_for_workspace(db, workspace_id=workspace_id)
    if current >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plan limit reached: max {limit} documents.",
        )


def enforce_bot_limit(db: Session, workspace_id: int) -> None:
    billing = enforce_subscription_active(db, workspace_id)
    limit = get_plan_limits(billing["plan"]).max_bots
    if limit is None:
        return
    current = repo.count_bots_for_workspace(db, workspace_id=workspace_id)
    if current >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plan limit reached: max {limit} bots.",
        )


def enforce_model_allowed(db: Session, workspace_id: int, model_name: str | None) -> None:
    billing = enforce_subscription_active(db, workspace_id)
    allowed = get_plan_limits(billing["plan"]).allowed_models
    if allowed is None:
        return
    normalized = normalize_model_name(model_name)
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{normalized}' is not available on '{billing['plan']}' plan.",
        )


def enforce_message_limit(db: Session, workspace_id: int) -> None:
    billing = enforce_subscription_active(db, workspace_id)
    limit = get_plan_limits(billing["plan"]).max_messages
    if limit is None:
        return
    current = repo.count_messages_for_workspace(db, workspace_id=workspace_id)
    if current >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plan limit reached: max {limit} messages.",
        )


def enforce_positive_balance(db: Session, workspace_id: int) -> dict:
    billing = enforce_subscription_active(db, workspace_id)
    if Decimal(billing["balance_usd"]) <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient balance. Top up your workspace to continue chatting.",
        )
    return billing
