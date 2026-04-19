from __future__ import annotations

import ast
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, case, delete, func, or_, select, text, update
from sqlalchemy.orm import Session, aliased

from app.db import models as m


# -----------------------------------------------------------------------------
# Row helpers (API-compatible dicts)
# -----------------------------------------------------------------------------
def _user_to_dict(row: m.User) -> dict:
    return {
        "id": row.id,
        "email": row.email,
        "hashed_password": row.hashed_password,
        "full_name": row.full_name,
        "is_active": row.is_active,
        "created_at": row.created_at,
    }


def _workspace_to_dict(row: m.Workspace) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "owner_id": row.owner_id,
        "created_at": row.created_at,
    }


def _normalize_bot_response(bot: dict) -> dict:
    if bot and "temperature" in bot:
        t = bot["temperature"]
        if isinstance(t, Decimal):
            bot["temperature"] = str(float(t))
        elif hasattr(t, "__float__"):
            bot["temperature"] = str(float(t))
        else:
            bot["temperature"] = str(t)

    if bot and "config" in bot and isinstance(bot["config"], dict):
        config = bot["config"]
        nodes = config.get("nodes")
        if isinstance(nodes, str):
            try:
                config["nodes"] = json.loads(nodes)
            except (json.JSONDecodeError, TypeError):
                try:
                    config["nodes"] = ast.literal_eval(nodes)
                except (ValueError, SyntaxError):
                    pass
        if not isinstance(config.get("nodes"), list):
            if isinstance(config.get("nodes"), dict):
                config["nodes"] = [config["nodes"]]
            else:
                config["nodes"] = []
    return bot


def _build_config_dict(config_rows: list[m.BotConfig]) -> dict:
    config: dict = {}
    for row in config_rows:
        key = row.config_key
        value = row.config_value
        value_type = row.value_type
        if value_type == "number":
            try:
                config[key] = float(value) if "." in value else int(value)
            except ValueError:
                config[key] = value
        elif value_type == "boolean":
            config[key] = value.lower() in ("true", "1", "yes")
        elif value_type in ("array", "object"):
            try:
                config[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                try:
                    config[key] = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    config[key] = value
        else:
            config[key] = value
    return config


def _build_headers_dict(rows: list[m.ApiToolHeader]) -> dict:
    return {r.header_key: r.header_value for r in rows}


def _build_params_dict(rows: list[m.ApiToolParam]) -> dict:
    params: dict = {}
    for row in rows:
        key = row.param_key
        val = row.param_value
        ptype = row.param_type
        if val is None:
            params[key] = None
        elif ptype == "number":
            try:
                params[key] = float(val) if "." in val else int(val)
            except ValueError:
                params[key] = val
        elif ptype == "boolean":
            params[key] = val.lower() in ("true", "1", "yes")
        else:
            params[key] = val
    return params


def _build_body_schema_dict(rows: list[m.ApiToolBodyField]) -> dict:
    schema: dict = {}
    for row in rows:
        if row.parent_field_id is None:
            field_info: dict = {"type": row.field_type, "required": row.is_required}
            if row.description:
                field_info["description"] = row.description
            schema[row.field_name] = field_info
    return schema


def _build_metadata_dict(rows: list[m.ChatMessageMetadata]) -> dict:
    return {r.metadata_key: r.metadata_value for r in rows}


def _bot_to_dict(bot: m.Bot, config_rows: list[m.BotConfig]) -> dict:
    d = {
        "id": bot.id,
        "name": bot.name,
        "workspace_id": bot.workspace_id,
        "system_prompt": bot.system_prompt,
        "temperature": bot.temperature,
        "max_tokens": bot.max_tokens,
        "created_at": bot.created_at,
        "updated_at": bot.updated_at,
        "config": _build_config_dict(config_rows),
    }
    return _normalize_bot_response(d)


def _document_to_dict(doc: m.Document) -> dict:
    return {
        "id": doc.id,
        "workspace_id": doc.workspace_id,
        "filename": doc.filename,
        "file_path": doc.file_path,
        "file_size": doc.file_size,
        "file_type": doc.file_type,
        "status": doc.status,
        "error_message": doc.error_message,
        "created_at": doc.created_at,
        "processed_at": doc.processed_at,
    }


def _api_tool_to_dict(
    tool: m.ApiTool,
    headers: list[m.ApiToolHeader],
    params: list[m.ApiToolParam],
    body_fields: list[m.ApiToolBodyField],
) -> dict:
    d = {
        "id": tool.id,
        "workspace_id": tool.workspace_id,
        "name": tool.name,
        "description": tool.description,
        "url": tool.url,
        "method": tool.method,
        "created_at": tool.created_at,
        "headers": _build_headers_dict(headers),
        "params": _build_params_dict(params),
        "body_schema": _build_body_schema_dict(body_fields),
    }
    return d


# -----------------------------------------------------------------------------
# Users
# -----------------------------------------------------------------------------
def get_user_by_email(db: Session, email: str) -> Optional[dict]:
    row = db.scalars(select(m.User).where(m.User.email == email)).first()
    return _user_to_dict(row) if row else None


def get_user_by_id(db: Session, user_id: int) -> Optional[dict]:
    row = db.get(m.User, user_id)
    return _user_to_dict(row) if row else None


def create_user(
    db: Session,
    *,
    email: str,
    hashed_password: str,
    full_name: Optional[str],
) -> dict:
    u = m.User(email=email, hashed_password=hashed_password, full_name=full_name)
    db.add(u)
    db.flush()
    return _user_to_dict(u)


# -----------------------------------------------------------------------------
# Workspaces
# -----------------------------------------------------------------------------
def create_workspace(db: Session, *, owner_id: int, name: str) -> dict:
    w = m.Workspace(name=name, owner_id=owner_id)
    db.add(w)
    db.flush()
    return _workspace_to_dict(w)


def get_workspace_for_owner(
    db: Session,
    *,
    workspace_id: int,
    owner_id: int,
) -> Optional[dict]:
    row = db.scalars(
        select(m.Workspace).where(
            m.Workspace.id == workspace_id,
            m.Workspace.owner_id == owner_id,
        )
    ).first()
    return _workspace_to_dict(row) if row else None


def list_workspaces_for_owner(db: Session, owner_id: int) -> list[dict]:
    rows = db.scalars(
        select(m.Workspace).where(m.Workspace.owner_id == owner_id).order_by(m.Workspace.created_at.desc())
    ).all()
    return [_workspace_to_dict(r) for r in rows]


def get_workspace_by_id(db: Session, workspace_id: int) -> Optional[dict]:
    row = db.get(m.Workspace, workspace_id)
    return _workspace_to_dict(row) if row else None


def add_user_to_workspace(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
    role: str = "member",
) -> dict:
    wu = m.WorkspaceUser(workspace_id=workspace_id, user_id=user_id, role=role)
    db.merge(wu)
    db.flush()
    return {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "role": role,
        "added_at": wu.added_at,
    }


def remove_user_from_workspace(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
) -> bool:
    r = db.execute(
        delete(m.WorkspaceUser).where(
            m.WorkspaceUser.workspace_id == workspace_id,
            m.WorkspaceUser.user_id == user_id,
        )
    )
    return r.rowcount > 0


def list_workspace_users(db: Session, workspace_id: int) -> list[dict]:
    stmt = (
        select(m.User.id, m.User.email, m.User.full_name, m.WorkspaceUser.role, m.WorkspaceUser.added_at)
        .join(m.WorkspaceUser, m.WorkspaceUser.user_id == m.User.id)
        .where(m.WorkspaceUser.workspace_id == workspace_id)
        .order_by(m.WorkspaceUser.added_at.desc())
    )
    out = []
    for uid, email, full_name, role, added_at in db.execute(stmt):
        out.append(
            {
                "id": uid,
                "email": email,
                "full_name": full_name,
                "role": role,
                "added_at": added_at,
            }
        )
    return out


def check_user_workspace_access(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
) -> Optional[dict]:
    wu = aliased(m.WorkspaceUser)
    user_role = case(
        (m.Workspace.owner_id == user_id, "owner"),
        (wu.user_id.isnot(None), wu.role),
        else_=None,
    )
    stmt = (
        select(m.Workspace, user_role.label("user_role"))
        .select_from(m.Workspace)
        .outerjoin(
            wu,
            and_(wu.workspace_id == m.Workspace.id, wu.user_id == user_id),
        )
        .where(m.Workspace.id == workspace_id)
        .where(or_(m.Workspace.owner_id == user_id, wu.user_id == user_id))
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


def list_all_workspaces_for_user(db: Session, user_id: int) -> list[dict]:
    owned = db.scalars(select(m.Workspace).where(m.Workspace.owner_id == user_id)).all()
    memberships = db.scalars(
        select(m.WorkspaceUser).where(m.WorkspaceUser.user_id == user_id)
    ).all()
    owner_ids = {w.id for w in owned}
    combined: dict[int, tuple[m.Workspace, str]] = {}
    for w in owned:
        combined[w.id] = (w, "owner")
    for mu in memberships:
        if mu.workspace_id in owner_ids:
            continue
        ws = db.get(m.Workspace, mu.workspace_id)
        if ws:
            combined[ws.id] = (ws, mu.role)
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


# -----------------------------------------------------------------------------
# Bots
# -----------------------------------------------------------------------------
def create_bot(
    db: Session,
    *,
    name: str,
    workspace_id: int,
    system_prompt: str,
    config: dict,
    temperature: str,
    max_tokens: int,
) -> dict:
    bot = m.Bot(
        name=name,
        workspace_id=workspace_id,
        system_prompt=system_prompt,
        temperature=float(temperature),
        max_tokens=max_tokens,
    )
    db.add(bot)
    db.flush()

    if config:
        for key, value in config.items():
            vt = type(value).__name__
            if vt in ("int", "float"):
                vt = "number"
                sv = str(value)
            elif vt == "bool":
                vt = "boolean"
                sv = str(value)
            elif vt in ("list", "tuple"):
                vt = "array"
                sv = json.dumps(value)
            elif vt == "dict":
                vt = "object"
                sv = json.dumps(value)
            else:
                vt = "string"
                sv = str(value)
            db.add(m.BotConfig(bot_id=bot.id, config_key=key, config_value=sv, value_type=vt))

    db.flush()
    cfg_rows = db.scalars(select(m.BotConfig).where(m.BotConfig.bot_id == bot.id)).all()
    return _bot_to_dict(bot, list(cfg_rows))


def _load_bot_configs(db: Session, bot_id: int) -> list[m.BotConfig]:
    return list(db.scalars(select(m.BotConfig).where(m.BotConfig.bot_id == bot_id)).all())


def list_bots_for_owner(
    db: Session,
    *,
    owner_id: int,
    workspace_id: Optional[int] = None,
) -> list[dict]:
    stmt = select(m.Bot).join(m.Workspace, m.Workspace.id == m.Bot.workspace_id).where(m.Workspace.owner_id == owner_id)
    if workspace_id is not None:
        stmt = stmt.where(m.Bot.workspace_id == workspace_id)
    stmt = stmt.order_by(m.Bot.created_at.desc())
    bots = db.scalars(stmt).all()
    out = []
    for b in bots:
        cfg = _load_bot_configs(db, b.id)
        out.append(_bot_to_dict(b, cfg))
    return out


def get_bot_for_owner(
    db: Session,
    *,
    bot_id: int,
    owner_id: int,
) -> Optional[dict]:
    b = db.scalars(
        select(m.Bot)
        .join(m.Workspace, m.Workspace.id == m.Bot.workspace_id)
        .where(m.Bot.id == bot_id, m.Workspace.owner_id == owner_id)
    ).first()
    if not b:
        return None
    return _bot_to_dict(b, _load_bot_configs(db, b.id))


def get_bot_by_id(db: Session, bot_id: int) -> Optional[dict]:
    b = db.get(m.Bot, bot_id)
    if not b:
        return None
    return _bot_to_dict(b, _load_bot_configs(db, b.id))


def list_bots_for_user(
    db: Session,
    *,
    user_id: int,
    workspace_id: Optional[int] = None,
) -> list[dict]:
    wu = aliased(m.WorkspaceUser)
    stmt = (
        select(m.Bot)
        .join(m.Workspace, m.Workspace.id == m.Bot.workspace_id)
        .outerjoin(wu, and_(wu.workspace_id == m.Workspace.id, wu.user_id == user_id))
        .where(or_(m.Workspace.owner_id == user_id, wu.user_id == user_id))
    )
    if workspace_id is not None:
        stmt = stmt.where(m.Bot.workspace_id == workspace_id)
    stmt = stmt.order_by(m.Bot.created_at.desc())
    bots = db.scalars(stmt).all()
    seen: set[int] = set()
    out = []
    for b in bots:
        if b.id in seen:
            continue
        seen.add(b.id)
        out.append(_bot_to_dict(b, _load_bot_configs(db, b.id)))
    return out


def get_bot_for_user(
    db: Session,
    *,
    bot_id: int,
    user_id: int,
) -> Optional[dict]:
    wu = aliased(m.WorkspaceUser)
    b = db.scalars(
        select(m.Bot)
        .join(m.Workspace, m.Workspace.id == m.Bot.workspace_id)
        .outerjoin(wu, and_(wu.workspace_id == m.Workspace.id, wu.user_id == user_id))
        .where(m.Bot.id == bot_id)
        .where(or_(m.Workspace.owner_id == user_id, wu.user_id == user_id))
    ).first()
    if not b:
        return None
    return _bot_to_dict(b, _load_bot_configs(db, b.id))


def update_bot_for_owner(
    db: Session,
    *,
    bot_id: int,
    owner_id: int,
    updates: Dict[str, Any],
) -> Optional[dict]:
    if not updates:
        return get_bot_for_owner(db, bot_id=bot_id, owner_id=owner_id)

    config = updates.pop("config", None)

    bot = db.scalars(
        select(m.Bot)
        .join(m.Workspace, m.Workspace.id == m.Bot.workspace_id)
        .where(m.Bot.id == bot_id, m.Workspace.owner_id == owner_id)
    ).first()
    if not bot:
        return None

    if updates:
        if "temperature" in updates:
            updates["temperature"] = float(updates["temperature"])
        for key, value in updates.items():
            setattr(bot, key, value)

    if config is not None:
        db.execute(delete(m.BotConfig).where(m.BotConfig.bot_id == bot_id))
        if config:
            for key, value in config.items():
                vt = type(value).__name__
                if vt in ("int", "float"):
                    vt = "number"
                    sv = str(value)
                elif vt == "bool":
                    vt = "boolean"
                    sv = str(value)
                elif vt in ("list", "tuple"):
                    vt = "array"
                    sv = json.dumps(value)
                elif vt == "dict":
                    vt = "object"
                    sv = json.dumps(value)
                else:
                    vt = "string"
                    sv = str(value)
                db.add(m.BotConfig(bot_id=bot_id, config_key=key, config_value=sv, value_type=vt))
        db.flush()

    cfg_rows = _load_bot_configs(db, bot_id)
    return _bot_to_dict(bot, cfg_rows)


def delete_bot_for_owner(
    db: Session,
    *,
    bot_id: int,
    owner_id: int,
) -> bool:
    subq = select(m.Workspace.id).where(m.Workspace.owner_id == owner_id).scalar_subquery()
    r = db.execute(delete(m.Bot).where(m.Bot.id == bot_id, m.Bot.workspace_id.in_(subq)))
    return r.rowcount > 0


# -----------------------------------------------------------------------------
# API tools
# -----------------------------------------------------------------------------
def _load_api_tool_parts(db: Session, tool_id: int) -> tuple[list[m.ApiToolHeader], list[m.ApiToolParam], list[m.ApiToolBodyField]]:
    headers = list(
        db.scalars(select(m.ApiToolHeader).where(m.ApiToolHeader.api_tool_id == tool_id)).all()
    )
    params = list(db.scalars(select(m.ApiToolParam).where(m.ApiToolParam.api_tool_id == tool_id)).all())
    fields = list(
        db.scalars(select(m.ApiToolBodyField).where(m.ApiToolBodyField.api_tool_id == tool_id)).all()
    )
    return headers, params, fields


def create_api_tool(
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
        for k, v in headers.items():
            db.add(m.ApiToolHeader(api_tool_id=tool.id, header_key=k, header_value=str(v)))
    if params:
        for k, v in params.items():
            pt = type(v).__name__
            if pt in ("int", "float"):
                pt = "number"
            elif pt == "bool":
                pt = "boolean"
            elif pt in ("list", "tuple"):
                pt = "array"
            else:
                pt = "string"
            db.add(
                m.ApiToolParam(
                    api_tool_id=tool.id,
                    param_key=k,
                    param_value=str(v) if v is not None else None,
                    param_type=pt,
                )
            )
    if body_schema:
        for fname, finfo in body_schema.items():
            if isinstance(finfo, dict):
                ft = finfo.get("type", "string")
                req = finfo.get("required", False)
                fd = finfo.get("description", "") or ""
            else:
                ft, req, fd = "string", False, ""
            db.add(
                m.ApiToolBodyField(
                    api_tool_id=tool.id,
                    field_name=fname,
                    field_type=ft,
                    is_required=req,
                    description=fd or None,
                )
            )
    db.flush()
    h, p, bf = _load_api_tool_parts(db, tool.id)
    return _api_tool_to_dict(tool, h, p, bf)


def list_api_tools_for_workspace(db: Session, workspace_id: int) -> list[dict]:
    tools = db.scalars(
        select(m.ApiTool).where(m.ApiTool.workspace_id == workspace_id).order_by(m.ApiTool.created_at.desc())
    ).all()
    out = []
    for t in tools:
        h, p, bf = _load_api_tool_parts(db, t.id)
        out.append(_api_tool_to_dict(t, h, p, bf))
    return out


def get_api_tool_for_owner(
    db: Session,
    *,
    tool_id: int,
    owner_id: int,
) -> Optional[dict]:
    t = db.scalars(
        select(m.ApiTool)
        .join(m.Workspace, m.Workspace.id == m.ApiTool.workspace_id)
        .where(m.ApiTool.id == tool_id, m.Workspace.owner_id == owner_id)
    ).first()
    if not t:
        return None
    h, p, bf = _load_api_tool_parts(db, t.id)
    return _api_tool_to_dict(t, h, p, bf)


def get_api_tool_for_user(
    db: Session,
    *,
    tool_id: int,
    user_id: int,
) -> Optional[dict]:
    wu = aliased(m.WorkspaceUser)
    t = db.scalars(
        select(m.ApiTool)
        .join(m.Workspace, m.Workspace.id == m.ApiTool.workspace_id)
        .outerjoin(wu, and_(wu.workspace_id == m.Workspace.id, wu.user_id == user_id))
        .where(m.ApiTool.id == tool_id)
        .where(or_(m.Workspace.owner_id == user_id, wu.user_id == user_id))
    ).first()
    if not t:
        return None
    h, p, bf = _load_api_tool_parts(db, t.id)
    return _api_tool_to_dict(t, h, p, bf)


def update_api_tool_for_owner(
    db: Session,
    *,
    tool_id: int,
    owner_id: int,
    updates: Dict[str, Any],
) -> Optional[dict]:
    if not updates:
        return get_api_tool_for_owner(db, tool_id=tool_id, owner_id=owner_id)

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
        for k, v in updates.items():
            setattr(tool, k, v)

    if headers is not None:
        db.execute(delete(m.ApiToolHeader).where(m.ApiToolHeader.api_tool_id == tool_id))
        for k, v in headers.items():
            db.add(m.ApiToolHeader(api_tool_id=tool_id, header_key=k, header_value=str(v)))

    if params is not None:
        db.execute(delete(m.ApiToolParam).where(m.ApiToolParam.api_tool_id == tool_id))
        for k, v in params.items():
            pt = type(v).__name__
            if pt in ("int", "float"):
                pt = "number"
            elif pt == "bool":
                pt = "boolean"
            elif pt in ("list", "tuple"):
                pt = "array"
            else:
                pt = "string"
            db.add(
                m.ApiToolParam(
                    api_tool_id=tool_id,
                    param_key=k,
                    param_value=str(v) if v is not None else None,
                    param_type=pt,
                )
            )

    if body_schema is not None:
        db.execute(delete(m.ApiToolBodyField).where(m.ApiToolBodyField.api_tool_id == tool_id))
        for fname, finfo in body_schema.items():
            if isinstance(finfo, dict):
                ft = finfo.get("type", "string")
                required_str = finfo.get("required")
                if required_str == "True":
                    required = True 
                else:
                    required = False

                fd = finfo.get("description", "") or ""
            else:
                ft, required, fd = "string", False, ""
            db.add(
                m.ApiToolBodyField(
                    api_tool_id=tool_id,
                    field_name=fname,
                    field_type=ft,
                    is_required=required,
                    description=fd or None,
                )
            )

    db.flush()
    h, p, bf = _load_api_tool_parts(db, tool_id)
    return _api_tool_to_dict(tool, h, p, bf)


def delete_api_tool_for_owner(
    db: Session,
    *,
    tool_id: int,
    owner_id: int,
) -> bool:
    subq = select(m.Workspace.id).where(m.Workspace.owner_id == owner_id).scalar_subquery()
    r = db.execute(delete(m.ApiTool).where(m.ApiTool.id == tool_id, m.ApiTool.workspace_id.in_(subq)))
    return r.rowcount > 0


def get_api_tools_by_ids(
    db: Session,
    *,
    workspace_id: int,
    tool_ids: Sequence[int],
) -> list[dict]:
    if not tool_ids:
        return []
    tools = db.scalars(
        select(m.ApiTool).where(m.ApiTool.workspace_id == workspace_id, m.ApiTool.id.in_(tool_ids))
    ).all()
    out = []
    for t in tools:
        h, p, bf = _load_api_tool_parts(db, t.id)
        out.append(_api_tool_to_dict(t, h, p, bf))
    return out


# -----------------------------------------------------------------------------
# Documents
# -----------------------------------------------------------------------------
def create_document(
    db: Session,
    *,
    workspace_id: int,
    filename: str,
    file_path: str,
    file_size: int,
    file_type: str,
    status: str = "processing",
) -> dict:
    doc = m.Document(
        workspace_id=workspace_id,
        filename=filename,
        file_path=file_path,
        file_size=file_size,
        file_type=file_type,
        status=status,
    )
    db.add(doc)
    db.flush()
    return _document_to_dict(doc)


def list_documents_for_workspace(db: Session, workspace_id: int) -> list[dict]:
    rows = db.scalars(
        select(m.Document).where(m.Document.workspace_id == workspace_id).order_by(m.Document.created_at.desc())
    ).all()
    return [_document_to_dict(r) for r in rows]


def get_document_for_owner(
    db: Session,
    *,
    document_id: int,
    owner_id: int,
) -> Optional[dict]:
    doc = db.scalars(
        select(m.Document)
        .join(m.Workspace, m.Workspace.id == m.Document.workspace_id)
        .where(m.Document.id == document_id, m.Workspace.owner_id == owner_id)
    ).first()
    return _document_to_dict(doc) if doc else None


def get_document_for_user(
    db: Session,
    *,
    document_id: int,
    user_id: int,
) -> Optional[dict]:
    wu = aliased(m.WorkspaceUser)
    doc = db.scalars(
        select(m.Document)
        .join(m.Workspace, m.Workspace.id == m.Document.workspace_id)
        .outerjoin(wu, and_(wu.workspace_id == m.Workspace.id, wu.user_id == user_id))
        .where(m.Document.id == document_id)
        .where(or_(m.Workspace.owner_id == user_id, wu.user_id == user_id))
    ).first()
    return _document_to_dict(doc) if doc else None


def get_document_by_id(db: Session, document_id: int) -> Optional[dict]:
    doc = db.get(m.Document, document_id)
    return _document_to_dict(doc) if doc else None


def list_document_chunk_ids(db: Session, document_id: int) -> list[int]:
    rows = db.scalars(select(m.DocumentChunk.id).where(m.DocumentChunk.document_id == document_id)).all()
    return list(rows)


def list_chunk_embedding_ids(db: Session, document_id: int) -> list[str]:
    rows = db.scalars(
        select(m.DocumentChunk.embedding_id).where(
            m.DocumentChunk.document_id == document_id,
            m.DocumentChunk.embedding_id.isnot(None),
        )
    ).all()
    return [r for r in rows if r]


def insert_document_chunk(
    db: Session,
    *,
    document_id: int,
    chunk_text: str,
    chunk_index: int,
) -> dict:
    ch = m.DocumentChunk(document_id=document_id, chunk_text=chunk_text, chunk_index=chunk_index)
    db.add(ch)
    db.flush()
    return {
        "id": ch.id,
        "document_id": ch.document_id,
        "chunk_text": ch.chunk_text,
        "chunk_index": ch.chunk_index,
        "created_at": ch.created_at,
    }


def update_chunk_embedding_id(db: Session, *, chunk_id: int, embedding_id: str) -> None:
    db.execute(
        update(m.DocumentChunk).where(m.DocumentChunk.id == chunk_id).values(embedding_id=embedding_id)
    )


def update_document_status(
    db: Session,
    *,
    document_id: int,
    status: str,
    processed_at: Optional[datetime] = None,
    error_message: Optional[str] = None,
) -> Optional[dict]:
    doc = db.get(m.Document, document_id)
    if not doc:
        return None
    doc.status = status
    doc.processed_at = processed_at
    doc.error_message = error_message
    db.flush()
    return _document_to_dict(doc)


def delete_document_by_id(db: Session, document_id: int) -> bool:
    r = db.execute(delete(m.Document).where(m.Document.id == document_id))
    return r.rowcount > 0


# -----------------------------------------------------------------------------
# Chat sessions & messages
# -----------------------------------------------------------------------------
def create_chat_session(
    db: Session,
    *,
    bot_id: int,
    user_id: int,
) -> dict:
    s = m.ChatSession(bot_id=bot_id, user_id=user_id)
    db.add(s)
    db.flush()
    return {
        "id": s.id,
        "bot_id": s.bot_id,
        "user_id": s.user_id,
        "created_at": s.created_at,
        "last_activity_at": s.last_activity_at,
        "message_count": s.message_count,
    }


def get_chat_session_for_user(
    db: Session,
    *,
    session_id: int,
    user_id: int,
    bot_id: Optional[int] = None,
) -> Optional[dict]:
    stmt = select(m.ChatSession).where(m.ChatSession.id == session_id, m.ChatSession.user_id == user_id)
    if bot_id is not None:
        stmt = stmt.where(m.ChatSession.bot_id == bot_id)
    s = db.scalars(stmt).first()
    if not s:
        return None
    return {
        "id": s.id,
        "bot_id": s.bot_id,
        "user_id": s.user_id,
        "created_at": s.created_at,
        "last_activity_at": s.last_activity_at,
        "message_count": s.message_count,
    }


def list_chat_sessions_for_user(
    db: Session,
    *,
    user_id: int,
    bot_id: Optional[int] = None,
) -> list[dict]:
    stmt = select(m.ChatSession).where(m.ChatSession.user_id == user_id)
    if bot_id is not None:
        stmt = stmt.where(m.ChatSession.bot_id == bot_id)
    stmt = stmt.order_by(m.ChatSession.last_activity_at.desc(), m.ChatSession.created_at.desc())
    rows = db.scalars(stmt).all()
    out = []
    for s in rows:
        out.append(
            {
                "id": s.id,
                "bot_id": s.bot_id,
                "user_id": s.user_id,
                "created_at": s.created_at,
                "last_activity_at": s.last_activity_at,
                "message_count": s.message_count,
            }
        )
    return out


def insert_chat_message(
    db: Session,
    *,
    session_id: int,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> dict:
    filtered_metadata = None
    if metadata:
        filtered_metadata = {k: v for k, v in metadata.items() if v is not None}
        if not filtered_metadata:
            filtered_metadata = None

    row = db.execute(
        text("SELECT * FROM create_chat_message(:sid, :role, :content, :meta)"),
        {
            "sid": session_id,
            "role": role,
            "content": content,
            "meta": json.dumps(filtered_metadata) if filtered_metadata else None,
        },
    ).mappings().one()

    msg = {k: row[k] for k in row.keys()}
    if metadata:
        msg["message_metadata"] = metadata
    return msg


def list_messages_for_session(db: Session, session_id: int) -> list[dict]:
    messages = db.scalars(
        select(m.ChatMessage).where(m.ChatMessage.session_id == session_id).order_by(m.ChatMessage.created_at.asc())
    ).all()
    out = []
    for cm in messages:
        meta_rows = db.scalars(
            select(m.ChatMessageMetadata).where(m.ChatMessageMetadata.message_id == cm.id)
        ).all()
        d = {
            "id": cm.id,
            "session_id": cm.session_id,
            "role": cm.role,
            "content": cm.content,
            "created_at": cm.created_at,
            "message_metadata": _build_metadata_dict(list(meta_rows)),
        }
        out.append(d)
    return out


# -----------------------------------------------------------------------------
# Audit Logs
# -----------------------------------------------------------------------------
def list_audit_logs(
    db: Session,
    *,
    user_id: Optional[int] = None,
    table_name: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    stmt = (
        select(
            m.AuditLog,
            m.User.email.label("user_email"),
            m.User.full_name.label("user_name"),
        )
        .select_from(m.AuditLog)
        .outerjoin(m.User, m.User.id == m.AuditLog.user_id)
        .order_by(m.AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if user_id:
        stmt = stmt.where(m.AuditLog.user_id == user_id)
    if table_name:
        stmt = stmt.where(m.AuditLog.table_name == table_name)
    if action:
        stmt = stmt.where(m.AuditLog.action == action)

    out = []
    for al, email, name in db.execute(stmt):
        d = {
            "id": al.id,
            "user_id": al.user_id,
            "action": al.action,
            "table_name": al.table_name,
            "record_id": al.record_id,
            "old_data": al.old_data,
            "new_data": al.new_data,
            "ip_address": al.ip_address,
            "user_agent": al.user_agent,
            "created_at": al.created_at,
            "user_email": email,
            "user_name": name,
        }
        out.append(d)
    return out


def get_audit_log_by_id(db: Session, log_id: int) -> Optional[dict]:
    row = db.execute(
        select(
            m.AuditLog,
            m.User.email.label("user_email"),
            m.User.full_name.label("user_name"),
        )
        .select_from(m.AuditLog)
        .outerjoin(m.User, m.User.id == m.AuditLog.user_id)
        .where(m.AuditLog.id == log_id)
    ).first()
    if not row:
        return None
    al, email, name = row
    return {
        "id": al.id,
        "user_id": al.user_id,
        "action": al.action,
        "table_name": al.table_name,
        "record_id": al.record_id,
        "old_data": al.old_data,
        "new_data": al.new_data,
        "ip_address": al.ip_address,
        "user_agent": al.user_agent,
        "created_at": al.created_at,
        "user_email": email,
        "user_name": name,
    }


def count_audit_logs(
    db: Session,
    *,
    user_id: Optional[int] = None,
    table_name: Optional[str] = None,
    action: Optional[str] = None,
) -> int:
    stmt = select(func.count()).select_from(m.AuditLog)
    if user_id:
        stmt = stmt.where(m.AuditLog.user_id == user_id)
    if table_name:
        stmt = stmt.where(m.AuditLog.table_name == table_name)
    if action:
        stmt = stmt.where(m.AuditLog.action == action)
    return int(db.scalar(stmt) or 0)
