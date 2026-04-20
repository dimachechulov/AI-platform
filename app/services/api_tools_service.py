from __future__ import annotations

from typing import Dict, Optional

from fastapi import HTTPException, status

from app.db.database import DatabaseSession
from app.db.api_tool_repository import ApiToolRepository

ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


class ApiToolsService:
    def __init__(self, repository: ApiToolRepository):
        self.repository = repository

    def create_api_tool(
        self,
        db: DatabaseSession,
        *,
        workspace_id: int,
        name: str,
        description: Optional[str],
        url: str,
        method: str,
        headers: Optional[dict],
        params: Optional[dict],
        body_schema: Optional[dict],
    ) -> dict:
        normalized_method = self._normalize_method(method)
        tool = self.repository.create_api_tool(
            db,
            workspace_id=workspace_id,
            name=name,
            description=description,
            url=url,
            method=normalized_method,
            headers=headers,
            params=params,
            body_schema=body_schema,
        )
        db.commit()
        return tool

    def list_api_tools_for_workspace(self, db: DatabaseSession, workspace_id: int) -> list[dict]:
        return self.repository.list_api_tools_for_workspace(db, workspace_id)

    def get_api_tool_for_user(self, db: DatabaseSession, *, tool_id: int, user_id: int) -> dict:
        tool = self.repository.get_api_tool_for_user(db, tool_id=tool_id, user_id=user_id)
        if tool:
            return tool
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API tool not found",
        )

    def update_api_tool_for_owner(
        self,
        db: DatabaseSession,
        *,
        tool_id: int,
        owner_id: int,
        name: Optional[str],
        description: Optional[str],
        url: Optional[str],
        method: Optional[str],
        headers: Optional[dict],
        params: Optional[dict],
        body_schema: Optional[dict],
    ) -> dict:
        existing_tool = self.repository.get_api_tool_for_owner(db, tool_id=tool_id, owner_id=owner_id)
        if not existing_tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API tool not found",
            )

        updates: Dict[str, object] = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if url is not None:
            updates["url"] = url
        if method is not None:
            updates["method"] = self._normalize_method(method)
        if headers is not None:
            updates["headers"] = headers
        if params is not None:
            updates["params"] = params
        if body_schema is not None:
            updates["body_schema"] = body_schema

        updated_tool = self.repository.update_api_tool_for_owner(
            db,
            tool_id=tool_id,
            owner_id=owner_id,
            updates=updates,
        )
        if not updated_tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API tool not found",
            )
        db.commit()
        return updated_tool

    def delete_api_tool_for_owner(self, db: DatabaseSession, *, tool_id: int, owner_id: int) -> None:
        deleted = self.repository.delete_api_tool_for_owner(db, tool_id=tool_id, owner_id=owner_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API tool not found",
            )
        db.commit()

    @staticmethod
    def _normalize_method(method: str) -> str:
        normalized = method.upper()
        if normalized in ALLOWED_HTTP_METHODS:
            return normalized
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid HTTP method",
        )
