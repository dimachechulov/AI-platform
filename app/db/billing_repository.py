from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models as m
from app.db.repository_utils import billing_transaction_to_dict, workspace_billing_to_dict


class BillingRepository:
    def get_workspace_billing(self, db: Session, *, workspace_id: int) -> Optional[dict]:
        row = db.get(m.WorkspaceBilling, workspace_id)
        return workspace_billing_to_dict(row) if row else None

    def ensure_workspace_billing(self, db: Session, *, workspace_id: int) -> dict:
        row = db.get(m.WorkspaceBilling, workspace_id)
        if not row:
            row = m.WorkspaceBilling(
                workspace_id=workspace_id,
                plan="trial",
                subscription_status="trialing",
                trial_started_at=datetime.now(timezone.utc),
                trial_ends_at=datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=settings.TRIAL_DAYS),
                balance_usd=Decimal("1.0000"),
            )
            db.add(row)
            db.flush()
            row = db.get(m.WorkspaceBilling, workspace_id)
        return workspace_billing_to_dict(row)

    def get_workspace_billing_by_customer_id(self, db: Session, *, stripe_customer_id: str) -> Optional[dict]:
        row = db.scalars(
            select(m.WorkspaceBilling).where(m.WorkspaceBilling.stripe_customer_id == stripe_customer_id)
        ).first()
        return workspace_billing_to_dict(row) if row else None

    def get_workspace_billing_by_subscription_id(
        self,
        db: Session,
        *,
        stripe_subscription_id: str,
    ) -> Optional[dict]:
        row = db.scalars(
            select(m.WorkspaceBilling).where(m.WorkspaceBilling.stripe_subscription_id == stripe_subscription_id)
        ).first()
        return workspace_billing_to_dict(row) if row else None

    def update_workspace_billing(self, db: Session, *, workspace_id: int, updates: Dict[str, Any]) -> Optional[dict]:
        row = db.get(m.WorkspaceBilling, workspace_id)
        if not row:
            return None
        for key, value in updates.items():
            setattr(row, key, value)
        db.flush()
        return workspace_billing_to_dict(row)

    def create_billing_transaction(
        self,
        db: Session,
        *,
        workspace_id: int,
        transaction_type: str,
        amount_usd: Decimal,
        description: Optional[str] = None,
        related_message_id: Optional[int] = None,
        stripe_event_id: Optional[str] = None,
        metadata_json: Optional[dict] = None,
    ) -> dict:
        row = m.BillingTransaction(
            workspace_id=workspace_id,
            transaction_type=transaction_type,
            amount_usd=amount_usd,
            description=description,
            related_message_id=related_message_id,
            stripe_event_id=stripe_event_id,
            metadata_json=metadata_json,
        )
        db.add(row)
        db.flush()
        return billing_transaction_to_dict(row)

    def list_billing_transactions(self, db: Session, *, workspace_id: int, limit: int = 100) -> list[dict]:
        rows = db.scalars(
            select(m.BillingTransaction)
            .where(m.BillingTransaction.workspace_id == workspace_id)
            .order_by(m.BillingTransaction.created_at.desc())
            .limit(limit)
        ).all()
        return [billing_transaction_to_dict(row) for row in rows]

    def has_billing_transaction_for_stripe_event(self, db: Session, *, stripe_event_id: str) -> bool:
        count = db.scalar(
            select(func.count()).select_from(m.BillingTransaction).where(m.BillingTransaction.stripe_event_id == stripe_event_id)
        )
        return bool(count)

    def adjust_workspace_balance(
        self,
        db: Session,
        *,
        workspace_id: int,
        amount_delta: Decimal,
    ) -> Optional[dict]:
        row = db.get(m.WorkspaceBilling, workspace_id)
        if not row:
            return None
        row.balance_usd = Decimal(row.balance_usd) + Decimal(amount_delta)
        db.flush()
        return workspace_billing_to_dict(row)

    def count_documents_for_workspace(self, db: Session, *, workspace_id: int) -> int:
        count = db.scalar(select(func.count()).select_from(m.Document).where(m.Document.workspace_id == workspace_id))
        return int(count or 0)

    def count_bots_for_workspace(self, db: Session, *, workspace_id: int) -> int:
        count = db.scalar(select(func.count()).select_from(m.Bot).where(m.Bot.workspace_id == workspace_id))
        return int(count or 0)

    def count_messages_for_workspace(self, db: Session, *, workspace_id: int) -> int:
        count = db.scalar(
            select(func.count())
            .select_from(m.ChatMessage)
            .join(m.ChatSession, m.ChatSession.id == m.ChatMessage.session_id)
            .join(m.Bot, m.Bot.id == m.ChatSession.bot_id)
            .where(m.Bot.workspace_id == workspace_id, m.ChatMessage.role == "user")
        )
        return int(count or 0)

    def get_spending_totals(
        self,
        db: Session,
        *,
        workspace_id: int,
        time_from: datetime,
        time_to: datetime,
    ) -> Dict[str, Decimal]:
        row = db.execute(
            text(
                """
SELECT COALESCE(SUM(CASE WHEN amount_usd < 0 THEN -amount_usd ELSE 0 END), 0) AS spent_usd,
       COALESCE(SUM(CASE WHEN amount_usd > 0 THEN amount_usd ELSE 0 END), 0) AS topped_up_usd
FROM billing_transactions
WHERE workspace_id = :workspace_id
  AND created_at >= :time_from
  AND created_at < :time_to
"""
            ),
            {"workspace_id": workspace_id, "time_from": time_from, "time_to": time_to},
        ).mappings().one()
        return {"spent_usd": Decimal(row["spent_usd"] or 0), "topped_up_usd": Decimal(row["topped_up_usd"] or 0)}

    def get_spending_buckets(
        self,
        db: Session,
        *,
        workspace_id: int,
        time_from: datetime,
        time_to: datetime,
        bucket_minutes: int,
    ) -> List[Dict[str, Any]]:
        rows = db.execute(
            text(
                """
WITH bucketed AS (
  SELECT
    date_trunc('hour', created_at)
      + (floor(extract(minute from created_at) / :bucket_minutes) * :bucket_minutes) * interval '1 minute' AS bucket_start,
    amount_usd
  FROM billing_transactions
  WHERE workspace_id = :workspace_id
    AND created_at >= :time_from
    AND created_at < :time_to
)
SELECT bucket_start,
       COALESCE(SUM(CASE WHEN amount_usd < 0 THEN -amount_usd ELSE 0 END), 0) AS spent_usd
FROM bucketed
GROUP BY bucket_start
ORDER BY bucket_start
"""
            ),
            {
                "workspace_id": workspace_id,
                "time_from": time_from,
                "time_to": time_to,
                "bucket_minutes": bucket_minutes,
            },
        ).mappings().all()
        return [{"bucket_start": row["bucket_start"], "spent_usd": Decimal(row["spent_usd"] or 0)} for row in rows]
