from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session, aliased

from app.db import models as m
from app.db.repository_utils import api_tool_to_dict, load_api_tool_parts


class ApiToolRepository:
    def create_api_tool(
        self,
        db: Session,
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
        tool = m.ApiTool(
            workspace_id=workspace_id,
            name=name,
            description=description,
            url=url,
            method=method.upper(),
        )
        db.add(tool)
        db.flush()

        if headers:
            for key, value in headers.items():
                db.add(m.ApiToolHeader(api_tool_id=tool.id, header_key=key, header_value=str(value)))
        if params:
            for key, value in params.items():
                param_type = type(value).__name__
                if param_type in ("int", "float"):
                    param_type = "number"
                elif param_type == "bool":
                    param_type = "boolean"
                elif param_type in ("list", "tuple"):
                    param_type = "array"
                else:
                    param_type = "string"
                db.add(
                    m.ApiToolParam(
                        api_tool_id=tool.id,
                        param_key=key,
                        param_value=str(value) if value is not None else None,
                        param_type=param_type,
                    )
                )
        if body_schema:
            for field_name, field_info in body_schema.items():
                if isinstance(field_info, dict):
                    field_type = field_info.get("type", "string")
                    required = field_info.get("required", False)
                    description_text = field_info.get("description", "") or ""
                else:
                    field_type, required, description_text = "string", False, ""
                db.add(
                    m.ApiToolBodyField(
                        api_tool_id=tool.id,
                        field_name=field_name,
                        field_type=field_type,
                        is_required=required,
                        description=description_text or None,
                    )
                )
        db.flush()
        headers_rows, params_rows, body_rows = load_api_tool_parts(db, tool.id)
        return api_tool_to_dict(tool, headers_rows, params_rows, body_rows)

    def list_api_tools_for_workspace(self, db: Session, workspace_id: int) -> list[dict]:
        tools = db.scalars(
            select(m.ApiTool).where(m.ApiTool.workspace_id == workspace_id).order_by(m.ApiTool.created_at.desc())
        ).all()
        out = []
        for tool in tools:
            headers_rows, params_rows, body_rows = load_api_tool_parts(db, tool.id)
            out.append(api_tool_to_dict(tool, headers_rows, params_rows, body_rows))
        return out

    def get_api_tool_for_user(self, db: Session, *, tool_id: int, user_id: int) -> Optional[dict]:
        workspace_user = aliased(m.WorkspaceUser)
        tool = db.scalars(
            select(m.ApiTool)
            .join(m.Workspace, m.Workspace.id == m.ApiTool.workspace_id)
            .outerjoin(workspace_user, and_(workspace_user.workspace_id == m.Workspace.id, workspace_user.user_id == user_id))
            .where(m.ApiTool.id == tool_id)
            .where(or_(m.Workspace.owner_id == user_id, workspace_user.user_id == user_id))
        ).first()
        if not tool:
            return None
        headers_rows, params_rows, body_rows = load_api_tool_parts(db, tool.id)
        return api_tool_to_dict(tool, headers_rows, params_rows, body_rows)

    def get_api_tool_for_owner(self, db: Session, *, tool_id: int, owner_id: int) -> Optional[dict]:
        tool = db.scalars(
            select(m.ApiTool)
            .join(m.Workspace, m.Workspace.id == m.ApiTool.workspace_id)
            .where(m.ApiTool.id == tool_id, m.Workspace.owner_id == owner_id)
        ).first()
        if not tool:
            return None
        headers_rows, params_rows, body_rows = load_api_tool_parts(db, tool.id)
        return api_tool_to_dict(tool, headers_rows, params_rows, body_rows)

    def update_api_tool_for_owner(
        self,
        db: Session,
        *,
        tool_id: int,
        owner_id: int,
        updates: Dict[str, object],
    ) -> Optional[dict]:
        if not updates:
            return self.get_api_tool_for_owner(db, tool_id=tool_id, owner_id=owner_id)

        headers = updates.pop("headers", None)
        params = updates.pop("params", None)
        body_schema = updates.pop("body_schema", None)
        tool = db.scalars(
            select(m.ApiTool)
            .join(m.Workspace, m.Workspace.id == m.ApiTool.workspace_id)
            .where(m.ApiTool.id == tool_id, m.Workspace.owner_id == owner_id)
        ).first()
        if not tool:
            return None

        if updates:
            if "method" in updates:
                updates["method"] = str(updates["method"]).upper()
            for key, value in updates.items():
                setattr(tool, key, value)

        if headers is not None:
            db.execute(delete(m.ApiToolHeader).where(m.ApiToolHeader.api_tool_id == tool_id))
            for key, value in headers.items():
                db.add(m.ApiToolHeader(api_tool_id=tool_id, header_key=key, header_value=str(value)))
        if params is not None:
            db.execute(delete(m.ApiToolParam).where(m.ApiToolParam.api_tool_id == tool_id))
            for key, value in params.items():
                param_type = type(value).__name__
                if param_type in ("int", "float"):
                    param_type = "number"
                elif param_type == "bool":
                    param_type = "boolean"
                elif param_type in ("list", "tuple"):
                    param_type = "array"
                else:
                    param_type = "string"
                db.add(
                    m.ApiToolParam(
                        api_tool_id=tool_id,
                        param_key=key,
                        param_value=str(value) if value is not None else None,
                        param_type=param_type,
                    )
                )
        if body_schema is not None:
            db.execute(delete(m.ApiToolBodyField).where(m.ApiToolBodyField.api_tool_id == tool_id))
            for field_name, field_info in body_schema.items():
                if isinstance(field_info, dict):
                    field_type = field_info.get("type", "string")
                    required_raw = field_info.get("required")
                    required = required_raw is True or required_raw == "True"
                    description_text = field_info.get("description", "") or ""
                else:
                    field_type, required, description_text = "string", False, ""
                db.add(
                    m.ApiToolBodyField(
                        api_tool_id=tool_id,
                        field_name=field_name,
                        field_type=field_type,
                        is_required=required,
                        description=description_text or None,
                    )
                )
        db.flush()
        headers_rows, params_rows, body_rows = load_api_tool_parts(db, tool_id)
        return api_tool_to_dict(tool, headers_rows, params_rows, body_rows)

    def delete_api_tool_for_owner(self, db: Session, *, tool_id: int, owner_id: int) -> bool:
        workspace_ids = select(m.Workspace.id).where(m.Workspace.owner_id == owner_id).scalar_subquery()
        result = db.execute(delete(m.ApiTool).where(m.ApiTool.id == tool_id, m.ApiTool.workspace_id.in_(workspace_ids)))
        return result.rowcount > 0

    def get_api_tools_by_ids(self, db: Session, tool_ids: Sequence[int], workspace_id: int) -> list[dict]:
        if not tool_ids:
            return []
        tools = db.scalars(
            select(m.ApiTool).where(m.ApiTool.workspace_id == workspace_id, m.ApiTool.id.in_(tool_ids))
        ).all()
        out = []
        for tool in tools:
            headers_rows, params_rows, body_rows = load_api_tool_parts(db, tool.id)
            out.append(api_tool_to_dict(tool, headers_rows, params_rows, body_rows))
        return out
