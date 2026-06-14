from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, case, delete, or_, select
from sqlalchemy.orm import Session, aliased

from app.db import models as m
from app.db.billing_repository import BillingRepository
from app.db.repository_utils import workspace_to_dict


class WorkspaceRepository:
    def __init__(self) -> None:
        self._billing_repo = BillingRepository()

    def create_workspace(self, db: Session, *, owner_id: int, name: str) -> dict:
        workspace = m.Workspace(name=name, owner_id=owner_id)
        db.add(workspace)
        db.flush()
        self._billing_repo.ensure_workspace_billing(db, workspace_id=workspace.id)
        return workspace_to_dict(workspace)

    def list_all_workspaces_for_user(self, db: Session, user_id: int) -> list[dict]:
        owned = db.scalars(select(m.Workspace).where(m.Workspace.owner_id == user_id)).all()
        memberships = db.scalars(select(m.WorkspaceUser).where(m.WorkspaceUser.user_id == user_id)).all()
        owner_ids = {w.id for w in owned}
        combined: dict[int, tuple[m.Workspace, str]] = {}
        for workspace in owned:
            combined[workspace.id] = (workspace, "owner")
        for membership in memberships:
            if membership.workspace_id in owner_ids:
                continue
            workspace = db.get(m.Workspace, membership.workspace_id)
            if workspace:
                combined[workspace.id] = (workspace, membership.role)
        items = sorted(combined.values(), key=lambda x: x[0].created_at, reverse=True)
        return [
            {
                "id": ws.id,
                "name": ws.name,
                "owner_id": ws.owner_id,
                "created_at": ws.created_at,
                "user_role": role,
            }
            for ws, role in items
        ]

    def check_user_workspace_access(self, db: Session, *, workspace_id: int, user_id: int) -> Optional[dict]:
        workspace_user = aliased(m.WorkspaceUser)
        user_role = case(
            (m.Workspace.owner_id == user_id, "owner"),
            (workspace_user.user_id.isnot(None), workspace_user.role),
            else_=None,
        )
        stmt = (
            select(m.Workspace, user_role.label("user_role"))
            .select_from(m.Workspace)
            .outerjoin(
                workspace_user,
                and_(workspace_user.workspace_id == m.Workspace.id, workspace_user.user_id == user_id),
            )
            .where(m.Workspace.id == workspace_id)
            .where(or_(m.Workspace.owner_id == user_id, workspace_user.user_id == user_id))
        )
        row = db.execute(stmt).first()
        if not row:
            return None
        ws, role = row[0], row[1]
        return {
            "id": ws.id,
            "name": ws.name,
            "owner_id": ws.owner_id,
            "created_at": ws.created_at,
            "user_role": role,
        }

    def get_workspace_for_owner(self, db: Session, *, workspace_id: int, owner_id: int) -> Optional[dict]:
        row = db.scalars(
            select(m.Workspace).where(m.Workspace.id == workspace_id, m.Workspace.owner_id == owner_id)
        ).first()
        return workspace_to_dict(row) if row else None

    def list_workspace_users(self, db: Session, workspace_id: int) -> list[dict]:
        stmt = (
            select(m.User.id, m.User.email, m.User.full_name, m.WorkspaceUser.role, m.WorkspaceUser.added_at)
            .join(m.WorkspaceUser, m.WorkspaceUser.user_id == m.User.id)
            .where(m.WorkspaceUser.workspace_id == workspace_id)
            .order_by(m.WorkspaceUser.added_at.desc())
        )
        result = []
        for uid, email, full_name, role, added_at in db.execute(stmt):
            result.append(
                {"id": uid, "email": email, "full_name": full_name, "role": role, "added_at": added_at}
            )
        return result

    def get_user_by_email(self, db: Session, email: str) -> Optional[dict]:
        row = db.scalars(select(m.User).where(m.User.email == email)).first()
        if not row:
            return None
        return {
            "id": row.id,
            "email": row.email,
            "hashed_password": row.hashed_password,
            "full_name": row.full_name,
            "is_active": row.is_active,
            "created_at": row.created_at,
        }

    def add_user_to_workspace(
        self,
        db: Session,
        *,
        workspace_id: int,
        user_id: int,
        role: str = "member",
    ) -> dict:
        workspace_user = m.WorkspaceUser(workspace_id=workspace_id, user_id=user_id, role=role)
        db.merge(workspace_user)
        db.flush()
        return {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": role,
            "added_at": workspace_user.added_at or datetime.now(timezone.utc),
        }

    def remove_user_from_workspace(self, db: Session, *, workspace_id: int, user_id: int) -> bool:
        result = db.execute(
            delete(m.WorkspaceUser).where(m.WorkspaceUser.workspace_id == workspace_id, m.WorkspaceUser.user_id == user_id)
        )
        return result.rowcount > 0
