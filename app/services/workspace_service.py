from __future__ import annotations

from datetime import datetime
from typing import Dict

from fastapi import HTTPException, status

from app.db.database import DatabaseSession
from app.db.workspace_repository import WorkspaceRepository


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepository):
        self.repository = repository

    def create_workspace(self, db: DatabaseSession, *, owner_id: int, name: str) -> dict:
        workspace = self.repository.create_workspace(db, owner_id=owner_id, name=name)
        db.commit()
        return workspace

    def list_user_workspaces(self, db: DatabaseSession, user_id: int) -> list[dict]:
        return self.repository.list_all_workspaces_for_user(db, user_id)

    def get_workspace_for_user(self, db: DatabaseSession, *, workspace_id: int, user_id: int) -> dict:
        workspace = self.repository.check_user_workspace_access(db, workspace_id=workspace_id, user_id=user_id)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found or access denied",
            )
        return workspace

    def list_workspace_users_for_owner(self, db: DatabaseSession, *, workspace_id: int, owner_id: int) -> list[dict]:
        self._ensure_workspace_owner(db, workspace_id=workspace_id, owner_id=owner_id, action="list users")
        return self.repository.list_workspace_users(db, workspace_id)

    def add_user_to_workspace(
        self,
        db: DatabaseSession,
        *,
        workspace_id: int,
        owner_user: Dict,
        user_email: str,
        role: str,
    ) -> dict:
        self._ensure_workspace_owner(db, workspace_id=workspace_id, owner_id=owner_user["id"], action="add users")
        user_to_add = self.repository.get_user_by_email(db, user_email)
        if not user_to_add:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email '{user_email}' not found",
            )
        if user_to_add["id"] == owner_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot add yourself as a member",
            )
        added = self.repository.add_user_to_workspace(
            db,
            workspace_id=workspace_id,
            user_id=user_to_add["id"],
            role=role,
        )
        db.commit()
        return {
            "id": user_to_add["id"],
            "email": user_to_add["email"],
            "full_name": user_to_add.get("full_name"),
            "role": role,
            "added_at": added.get("added_at", datetime.now()),
        }

    def remove_user_from_workspace(
        self,
        db: DatabaseSession,
        *,
        workspace_id: int,
        owner_id: int,
        user_id: int,
    ) -> None:
        self._ensure_workspace_owner(db, workspace_id=workspace_id, owner_id=owner_id, action="remove users")
        success = self.repository.remove_user_from_workspace(db, workspace_id=workspace_id, user_id=user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in workspace",
            )
        db.commit()

    def _ensure_workspace_owner(self, db: DatabaseSession, *, workspace_id: int, owner_id: int, action: str) -> None:
        workspace = self.repository.get_workspace_for_owner(db, workspace_id=workspace_id, owner_id=owner_id)
        if workspace:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only workspace owner can {action}",
        )
