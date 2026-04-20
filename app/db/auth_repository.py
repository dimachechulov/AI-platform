from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.db.billing_repository import BillingRepository
from app.db.repository_utils import user_to_dict, workspace_to_dict


class AuthRepository:
    def __init__(self) -> None:
        self._billing_repo = BillingRepository()

    def get_user_by_email(self, db: Session, email: str) -> Optional[dict]:
        row = db.scalars(select(m.User).where(m.User.email == email)).first()
        return user_to_dict(row) if row else None

    def create_user(
        self,
        db: Session,
        *,
        email: str,
        hashed_password: str,
        full_name: Optional[str],
    ) -> dict:
        user = m.User(email=email, hashed_password=hashed_password, full_name=full_name)
        db.add(user)
        db.flush()
        return user_to_dict(user)

    def create_workspace(self, db: Session, *, owner_id: int, name: str) -> dict:
        workspace = m.Workspace(name=name, owner_id=owner_id)
        db.add(workspace)
        db.flush()
        self._billing_repo.ensure_workspace_billing(db, workspace_id=workspace.id)
        return workspace_to_dict(workspace)

    def list_workspaces_for_owner(self, db: Session, owner_id: int) -> list[dict]:
        rows = db.scalars(
            select(m.Workspace).where(m.Workspace.owner_id == owner_id).order_by(m.Workspace.created_at.desc())
        ).all()
        return [workspace_to_dict(row) for row in rows]
