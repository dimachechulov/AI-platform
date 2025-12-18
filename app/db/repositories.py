from __future__ import annotations

import ast
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from app.db.database import DatabaseSession


# Helper functions for normalized schema
def _normalize_bot_response(bot: dict) -> dict:
    """Convert bot response to API format (Decimal -> str for temperature, normalize config)"""
    if bot and "temperature" in bot:
        # Convert Decimal to string for API compatibility
        if hasattr(bot["temperature"], "__float__"):
            bot["temperature"] = str(float(bot["temperature"]))
        else:
            bot["temperature"] = str(bot["temperature"])
    
    # Нормализуем config.nodes - убеждаемся, что это массив, а не строка
    if bot and "config" in bot and isinstance(bot["config"], dict):
        config = bot["config"]
        if "nodes" in config:
            nodes = config["nodes"]
            # Если nodes - строка, пытаемся распарсить
            if isinstance(nodes, str):
                import ast
                try:
                    # Сначала пробуем JSON
                    config["nodes"] = json.loads(nodes)
                except (json.JSONDecodeError, TypeError):
                    # Если не JSON, пробуем Python literal
                    try:
                        config["nodes"] = ast.literal_eval(nodes)
                    except (ValueError, SyntaxError):
                        # Если не получается, оставляем как есть (будет ошибка валидации)
                        pass
            # Убеждаемся, что nodes - это список
            if not isinstance(config.get("nodes"), list):
                # Если это не список, пытаемся исправить
                if isinstance(config.get("nodes"), dict):
                    # Если это один объект, оборачиваем в список
                    config["nodes"] = [config["nodes"]]
                else:
                    # Иначе делаем пустой список
                    config["nodes"] = []
    
    return bot


def _build_config_dict(config_rows: list[dict]) -> dict:
    """Build config dictionary from bot_config rows"""
    config = {}
    for row in config_rows:
        key = row["config_key"]
        value = row["config_value"]
        value_type = row["value_type"]
        
        if value_type == "number":
            try:
                config[key] = float(value) if "." in value else int(value)
            except ValueError:
                config[key] = value
        elif value_type == "boolean":
            config[key] = value.lower() in ("true", "1", "yes")
        elif value_type in ("array", "object"):
            # Parse JSON strings for arrays and objects
            try:
                config[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Если не JSON, пробуем Python literal (для совместимости со старыми данными)
                try:
                    config[key] = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    config[key] = value
        else:
            config[key] = value
    return config


def _build_headers_dict(header_rows: list[dict]) -> dict:
    """Build headers dictionary from api_tool_headers rows"""
    return {row["header_key"]: row["header_value"] for row in header_rows}


def _build_params_dict(param_rows: list[dict]) -> dict:
    """Build params dictionary from api_tool_params rows"""
    params = {}
    for row in param_rows:
        key = row["param_key"]
        value = row["param_value"]
        param_type = row["param_type"]
        
        if value is None:
            params[key] = None
        elif param_type == "number":
            try:
                params[key] = float(value) if "." in value else int(value)
            except ValueError:
                params[key] = value
        elif param_type == "boolean":
            params[key] = value.lower() in ("true", "1", "yes")
        else:
            params[key] = value
    return params


def _build_body_schema_dict(field_rows: list[dict]) -> dict:
    """Build body schema dictionary from api_tool_body_fields rows"""
    schema = {}
    for row in field_rows:
        if row["parent_field_id"] is None:
            field_info = {
                "type": row["field_type"],
                "required": row["is_required"]
            }
            if row["description"]:
                field_info["description"] = row["description"]
            schema[row["field_name"]] = field_info
    return schema


def _build_metadata_dict(metadata_rows: list[dict]) -> dict:
    """Build metadata dictionary from metadata rows"""
    return {row["metadata_key"]: row["metadata_value"] for row in metadata_rows}


# -----------------------------------------------------------------------------
# Users
# -----------------------------------------------------------------------------
def get_user_by_email(db: DatabaseSession, email: str) -> Optional[dict]:
    query = """
        SELECT id, email, hashed_password, full_name, is_active, created_at
        FROM users
        WHERE email = %s
        LIMIT 1
    """
    return db.fetch_one(query, (email,))


def get_user_by_id(db: DatabaseSession, user_id: int) -> Optional[dict]:
    query = """
        SELECT id, email, hashed_password, full_name, is_active, created_at
        FROM users
        WHERE id = %s
        LIMIT 1
    """
    return db.fetch_one(query, (user_id,))


def create_user(
    db: DatabaseSession,
    *,
    email: str,
    hashed_password: str,
    full_name: Optional[str],
) -> dict:
    query = """
        INSERT INTO users (email, hashed_password, full_name, is_active)
        VALUES (%s, %s, %s, TRUE)
        RETURNING id, email, hashed_password, full_name, is_active, created_at
    """
    return db.fetch_one(query, (email, hashed_password, full_name))


# -----------------------------------------------------------------------------
# Workspaces
# -----------------------------------------------------------------------------
def create_workspace(db: DatabaseSession, *, owner_id: int, name: str) -> dict:
    query = """
        INSERT INTO workspaces (name, owner_id)
        VALUES (%s, %s)
        RETURNING id, name, owner_id, created_at
    """
    return db.fetch_one(query, (name, owner_id))


def get_workspace_for_owner(
    db: DatabaseSession,
    *,
    workspace_id: int,
    owner_id: int,
) -> Optional[dict]:
    query = """
        SELECT id, name, owner_id, created_at
        FROM workspaces
        WHERE id = %s AND owner_id = %s
        LIMIT 1
    """
    return db.fetch_one(query, (workspace_id, owner_id))


def list_workspaces_for_owner(db: DatabaseSession, owner_id: int) -> list[dict]:
    query = """
        SELECT id, name, owner_id, created_at
        FROM workspaces
        WHERE owner_id = %s
        ORDER BY created_at DESC
    """
    return db.fetch_all(query, (owner_id,))


def get_workspace_by_id(db: DatabaseSession, workspace_id: int) -> Optional[dict]:
    query = """
        SELECT id, name, owner_id, created_at
        FROM workspaces
        WHERE id = %s
        LIMIT 1
    """
    return db.fetch_one(query, (workspace_id,))


def add_user_to_workspace(
    db: DatabaseSession,
    *,
    workspace_id: int,
    user_id: int,
    role: str = "member",
) -> dict:
    """Добавить пользователя в воркспейс"""
    query = """
        INSERT INTO workspace_users (workspace_id, user_id, role)
        VALUES (%s, %s, %s)
        ON CONFLICT (workspace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role
        RETURNING workspace_id, user_id, role, added_at
    """
    return db.fetch_one(query, (workspace_id, user_id, role))


def remove_user_from_workspace(
    db: DatabaseSession,
    *,
    workspace_id: int,
    user_id: int,
) -> bool:
    """Удалить пользователя из воркспейса"""
    query = """
        DELETE FROM workspace_users
        WHERE workspace_id = %s AND user_id = %s
        RETURNING workspace_id
    """
    result = db.fetch_one(query, (workspace_id, user_id))
    return result is not None


def list_workspace_users(db: DatabaseSession, workspace_id: int) -> list[dict]:
    """Получить список пользователей воркспейса"""
    query = """
        SELECT u.id, u.email, u.full_name, wu.role, wu.added_at
        FROM workspace_users wu
        JOIN users u ON u.id = wu.user_id
        WHERE wu.workspace_id = %s
        ORDER BY wu.added_at DESC
    """
    return db.fetch_all(query, (workspace_id,))


def check_user_workspace_access(
    db: DatabaseSession,
    *,
    workspace_id: int,
    user_id: int,
) -> Optional[dict]:
    """Проверить доступ пользователя к воркспейсу (владелец или участник)"""
    query = """
        SELECT w.id, w.name, w.owner_id, w.created_at,
               CASE
                   WHEN w.owner_id = %s THEN 'owner'
                   WHEN wu.role IS NOT NULL THEN wu.role
                   ELSE NULL
               END as user_role
        FROM workspaces w
        LEFT JOIN workspace_users wu ON wu.workspace_id = w.id AND wu.user_id = %s
        WHERE w.id = %s
          AND (w.owner_id = %s OR wu.user_id = %s)
        LIMIT 1
    """
    return db.fetch_one(query, (user_id, user_id, workspace_id, user_id, user_id))


def list_all_workspaces_for_user(db: DatabaseSession, user_id: int) -> list[dict]:
    """Получить все воркспейсы пользователя (владелец + участник)"""
    query = """
        SELECT DISTINCT w.id, w.name, w.owner_id, w.created_at,
               CASE
                   WHEN w.owner_id = %s THEN 'owner'
                   ELSE COALESCE(wu.role, 'member')
               END as user_role
        FROM workspaces w
        LEFT JOIN workspace_users wu ON wu.workspace_id = w.id AND wu.user_id = %s
        WHERE w.owner_id = %s OR wu.user_id = %s
        ORDER BY w.created_at DESC
    """
    return db.fetch_all(query, (user_id, user_id, user_id, user_id))


# -----------------------------------------------------------------------------
# Bots
# -----------------------------------------------------------------------------
def create_bot(
    db: DatabaseSession,
    *,
    name: str,
    workspace_id: int,
    system_prompt: str,
    config: dict,
    temperature: str,
    max_tokens: int,
) -> dict:
    # Insert bot
    query = """
        INSERT INTO bots (name, workspace_id, system_prompt, temperature, max_tokens)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
    """
    bot = db.fetch_one(
        query,
        (name, workspace_id, system_prompt, float(temperature), max_tokens),
    )
    
    # Insert config items
    if config:
        config_query = """
            INSERT INTO bot_config (bot_id, config_key, config_value, value_type)
            VALUES (%s, %s, %s, %s)
        """
        for key, value in config.items():
            value_type = type(value).__name__
            if value_type in ("int", "float"):
                value_type = "number"
                str_value = str(value)
            elif value_type == "bool":
                value_type = "boolean"
                str_value = str(value)
            elif value_type in ("list", "tuple"):
                value_type = "array"
                str_value = json.dumps(value)
            elif value_type == "dict":
                value_type = "object"
                str_value = json.dumps(value)
            else:
                value_type = "string"
                str_value = str(value)
            
            db.execute(config_query, (bot["id"], key, str_value, value_type))
    
    bot["config"] = config
    return _normalize_bot_response(bot)


def list_bots_for_owner(
    db: DatabaseSession,
    *,
    owner_id: int,
    workspace_id: Optional[int] = None,
) -> list[dict]:
    base_query = """
        SELECT bots.*
        FROM bots
        JOIN workspaces ON workspaces.id = bots.workspace_id
        WHERE workspaces.owner_id = %s
    """
    params: List[Any] = [owner_id]
    if workspace_id:
        base_query += " AND bots.workspace_id = %s"
        params.append(workspace_id)
    base_query += " ORDER BY bots.created_at DESC"
    
    bots = db.fetch_all(base_query, tuple(params))
    
    # Fetch config for each bot
    for bot in bots:
        config_query = "SELECT * FROM bot_config WHERE bot_id = %s"
        config_rows = db.fetch_all(config_query, (bot["id"],))
        bot["config"] = _build_config_dict(config_rows)
        _normalize_bot_response(bot)
    
    return bots


def get_bot_for_owner(
    db: DatabaseSession,
    *,
    bot_id: int,
    owner_id: int,
) -> Optional[dict]:
    query = """
        SELECT bots.*
        FROM bots
        JOIN workspaces ON workspaces.id = bots.workspace_id
        WHERE bots.id = %s AND workspaces.owner_id = %s
        LIMIT 1
    """
    bot = db.fetch_one(query, (bot_id, owner_id))
    
    if bot:
        config_query = "SELECT * FROM bot_config WHERE bot_id = %s"
        config_rows = db.fetch_all(config_query, (bot["id"],))
        bot["config"] = _build_config_dict(config_rows)
        _normalize_bot_response(bot)
    
    return bot


def get_bot_by_id(db: DatabaseSession, bot_id: int) -> Optional[dict]:
    query = "SELECT * FROM bots WHERE id = %s LIMIT 1"
    bot = db.fetch_one(query, (bot_id,))
    
    if bot:
        config_query = "SELECT * FROM bot_config WHERE bot_id = %s"
        config_rows = db.fetch_all(config_query, (bot["id"],))
        bot["config"] = _build_config_dict(config_rows)
        _normalize_bot_response(bot)
    
    return bot


def list_bots_for_user(
    db: DatabaseSession,
    *,
    user_id: int,
    workspace_id: Optional[int] = None,
) -> list[dict]:
    """Получить список ботов для пользователя (владелец или участник воркспейса)"""
    base_query = """
        SELECT DISTINCT bots.*
        FROM bots
        JOIN workspaces ON workspaces.id = bots.workspace_id
        LEFT JOIN workspace_users wu ON wu.workspace_id = workspaces.id AND wu.user_id = %s
        WHERE workspaces.owner_id = %s OR wu.user_id = %s
    """
    params: List[Any] = [user_id, user_id, user_id]
    if workspace_id:
        base_query += " AND bots.workspace_id = %s"
        params.append(workspace_id)
    base_query += " ORDER BY bots.created_at DESC"
    
    bots = db.fetch_all(base_query, tuple(params))
    
    # Fetch config for each bot
    for bot in bots:
        config_query = "SELECT * FROM bot_config WHERE bot_id = %s"
        config_rows = db.fetch_all(config_query, (bot["id"],))
        bot["config"] = _build_config_dict(config_rows)
        _normalize_bot_response(bot)
    
    return bots


def get_bot_for_user(
    db: DatabaseSession,
    *,
    bot_id: int,
    user_id: int,
) -> Optional[dict]:
    """Получить бота для пользователя (владелец или участник воркспейса)"""
    query = """
        SELECT bots.*
        FROM bots
        JOIN workspaces ON workspaces.id = bots.workspace_id
        LEFT JOIN workspace_users wu ON wu.workspace_id = workspaces.id AND wu.user_id = %s
        WHERE bots.id = %s
          AND (workspaces.owner_id = %s OR wu.user_id = %s)
        LIMIT 1
    """
    bot = db.fetch_one(query, (user_id, bot_id, user_id, user_id))
    
    if bot:
        config_query = "SELECT * FROM bot_config WHERE bot_id = %s"
        config_rows = db.fetch_all(config_query, (bot["id"],))
        bot["config"] = _build_config_dict(config_rows)
        _normalize_bot_response(bot)
    
    return bot


def update_bot_for_owner(
    db: DatabaseSession,
    *,
    bot_id: int,
    owner_id: int,
    updates: Dict[str, Any],
) -> Optional[dict]:
    if not updates:
        return get_bot_for_owner(db, bot_id=bot_id, owner_id=owner_id)

    # Extract config from updates
    config = updates.pop("config", None)
    
    # Convert temperature string to float if present
    if "temperature" in updates:
        updates["temperature"] = float(updates["temperature"])
    
    # Update bot fields
    if updates:
        columns: List[str] = []
        params: List[Any] = []
        for column, value in updates.items():
            columns.append(f"{column} = %s")
            params.append(value)

        params.extend([bot_id, owner_id])
        query = f"""
            UPDATE bots
            SET {', '.join(columns)}, updated_at = NOW()
            FROM workspaces
            WHERE bots.workspace_id = workspaces.id
              AND bots.id = %s
              AND workspaces.owner_id = %s
            RETURNING bots.*
        """
        bot = db.fetch_one(query, tuple(params))
    else:
        bot = get_bot_for_owner(db, bot_id=bot_id, owner_id=owner_id)
    
    # Update config if provided
    if config is not None and bot:
        # Delete old config
        delete_query = "DELETE FROM bot_config WHERE bot_id = %s"
        db.execute(delete_query, (bot_id,))
        
        # Insert new config
        if config:
            config_query = """
                INSERT INTO bot_config (bot_id, config_key, config_value, value_type)
                VALUES (%s, %s, %s, %s)
            """
            for key, value in config.items():
                value_type = type(value).__name__
                if value_type in ("int", "float"):
                    value_type = "number"
                    str_value = str(value)
                elif value_type == "bool":
                    value_type = "boolean"
                    str_value = str(value)
                elif value_type in ("list", "tuple"):
                    value_type = "array"
                    str_value = json.dumps(value)
                elif value_type == "dict":
                    value_type = "object"
                    str_value = json.dumps(value)
                else:
                    value_type = "string"
                    str_value = str(value)
                
                db.execute(config_query, (bot_id, key, str_value, value_type))
        
        bot["config"] = config
    elif bot:
        config_query = "SELECT * FROM bot_config WHERE bot_id = %s"
        config_rows = db.fetch_all(config_query, (bot["id"],))
        bot["config"] = _build_config_dict(config_rows)
    
    return _normalize_bot_response(bot) if bot else bot


def delete_bot_for_owner(
    db: DatabaseSession,
    *,
    bot_id: int,
    owner_id: int,
) -> bool:
    query = """
        DELETE FROM bots
        USING workspaces
        WHERE bots.workspace_id = workspaces.id
          AND bots.id = %s
          AND workspaces.owner_id = %s
        RETURNING bots.id
    """
    result = db.fetch_one(query, (bot_id, owner_id))
    return result is not None


# -----------------------------------------------------------------------------
# API tools
# -----------------------------------------------------------------------------
def create_api_tool(
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
    # Insert api_tool
    query = """
        INSERT INTO api_tools (workspace_id, name, description, url, method)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
    """
    tool = db.fetch_one(query, (workspace_id, name, description, url, method.upper()))
    
    # Insert headers
    if headers:
        header_query = """
            INSERT INTO api_tool_headers (api_tool_id, header_key, header_value)
            VALUES (%s, %s, %s)
        """
        for key, value in headers.items():
            db.execute(header_query, (tool["id"], key, str(value)))
    
    # Insert params
    if params:
        param_query = """
            INSERT INTO api_tool_params (api_tool_id, param_key, param_value, param_type)
            VALUES (%s, %s, %s, %s)
        """
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
            
            db.execute(param_query, (tool["id"], key, str(value) if value is not None else None, param_type))
    
    # Insert body_schema fields
    if body_schema:
        field_query = """
            INSERT INTO api_tool_body_fields (api_tool_id, field_name, field_type, is_required, description)
            VALUES (%s, %s, %s, %s, %s)
        """
        for field_name, field_info in body_schema.items():
            if isinstance(field_info, dict):
                field_type = field_info.get("type", "string")
                is_required = field_info.get("required", False)
                field_desc = field_info.get("description", "")
            else:
                field_type = "string"
                is_required = False
                field_desc = ""
            
            db.execute(field_query, (tool["id"], field_name, field_type, is_required, field_desc))
    
    tool["headers"] = headers or {}
    tool["params"] = params or {}
    tool["body_schema"] = body_schema or {}
    
    return tool


def list_api_tools_for_workspace(db: DatabaseSession, workspace_id: int) -> list[dict]:
    query = """
        SELECT *
        FROM api_tools
        WHERE workspace_id = %s
        ORDER BY created_at DESC
    """
    tools = db.fetch_all(query, (workspace_id,))
    
    for tool in tools:
        # Fetch headers
        header_query = "SELECT * FROM api_tool_headers WHERE api_tool_id = %s"
        header_rows = db.fetch_all(header_query, (tool["id"],))
        tool["headers"] = _build_headers_dict(header_rows)
        
        # Fetch params
        param_query = "SELECT * FROM api_tool_params WHERE api_tool_id = %s"
        param_rows = db.fetch_all(param_query, (tool["id"],))
        tool["params"] = _build_params_dict(param_rows)
        
        # Fetch body schema
        field_query = "SELECT * FROM api_tool_body_fields WHERE api_tool_id = %s"
        field_rows = db.fetch_all(field_query, (tool["id"],))
        tool["body_schema"] = _build_body_schema_dict(field_rows)
    
    return tools


def get_api_tool_for_owner(
    db: DatabaseSession,
    *,
    tool_id: int,
    owner_id: int,
) -> Optional[dict]:
    query = """
        SELECT api_tools.*
        FROM api_tools
        JOIN workspaces ON workspaces.id = api_tools.workspace_id
        WHERE api_tools.id = %s AND workspaces.owner_id = %s
        LIMIT 1
    """
    tool = db.fetch_one(query, (tool_id, owner_id))
    
    if tool:
        # Fetch headers
        header_query = "SELECT * FROM api_tool_headers WHERE api_tool_id = %s"
        header_rows = db.fetch_all(header_query, (tool["id"],))
        tool["headers"] = _build_headers_dict(header_rows)
        
        # Fetch params
        param_query = "SELECT * FROM api_tool_params WHERE api_tool_id = %s"
        param_rows = db.fetch_all(param_query, (tool["id"],))
        tool["params"] = _build_params_dict(param_rows)
        
        # Fetch body schema
        field_query = "SELECT * FROM api_tool_body_fields WHERE api_tool_id = %s"
        field_rows = db.fetch_all(field_query, (tool["id"],))
        tool["body_schema"] = _build_body_schema_dict(field_rows)
    
    return tool


def get_api_tool_for_user(
    db: DatabaseSession,
    *,
    tool_id: int,
    user_id: int,
) -> Optional[dict]:
    """Получить API tool для пользователя (владелец или участник воркспейса)"""
    query = """
        SELECT api_tools.*
        FROM api_tools
        JOIN workspaces ON workspaces.id = api_tools.workspace_id
        LEFT JOIN workspace_users wu ON wu.workspace_id = workspaces.id AND wu.user_id = %s
        WHERE api_tools.id = %s
          AND (workspaces.owner_id = %s OR wu.user_id = %s)
        LIMIT 1
    """
    tool = db.fetch_one(query, (user_id, tool_id, user_id, user_id))
    
    if tool:
        # Fetch headers
        header_query = "SELECT * FROM api_tool_headers WHERE api_tool_id = %s"
        header_rows = db.fetch_all(header_query, (tool["id"],))
        tool["headers"] = _build_headers_dict(header_rows)
        
        # Fetch params
        param_query = "SELECT * FROM api_tool_params WHERE api_tool_id = %s"
        param_rows = db.fetch_all(param_query, (tool["id"],))
        tool["params"] = _build_params_dict(param_rows)
        
        # Fetch body schema
        field_query = "SELECT * FROM api_tool_body_fields WHERE api_tool_id = %s"
        field_rows = db.fetch_all(field_query, (tool["id"],))
        tool["body_schema"] = _build_body_schema_dict(field_rows)
    
    return tool


def update_api_tool_for_owner(
    db: DatabaseSession,
    *,
    tool_id: int,
    owner_id: int,
    updates: Dict[str, Any],
) -> Optional[dict]:
    if not updates:
        return get_api_tool_for_owner(db, tool_id=tool_id, owner_id=owner_id)

    # Extract special fields
    headers = updates.pop("headers", None)
    params = updates.pop("params", None)
    body_schema = updates.pop("body_schema", None)
    
    # Update main fields
    if updates:
        if "method" in updates:
            updates["method"] = updates["method"].upper()
        
        columns: List[str] = []
        params_list: List[Any] = []
        for column, value in updates.items():
            columns.append(f"{column} = %s")
            params_list.append(value)

        params_list.extend([tool_id, owner_id])
        query = f"""
            UPDATE api_tools
            SET {', '.join(columns)}
            FROM workspaces
            WHERE api_tools.workspace_id = workspaces.id
              AND api_tools.id = %s
              AND workspaces.owner_id = %s
            RETURNING api_tools.*
        """
        tool = db.fetch_one(query, tuple(params_list))
    else:
        tool = get_api_tool_for_owner(db, tool_id=tool_id, owner_id=owner_id)
    
    if not tool:
        return None
    
    # Update headers
    if headers is not None:
        db.execute("DELETE FROM api_tool_headers WHERE api_tool_id = %s", (tool_id,))
        if headers:
            header_query = """
                INSERT INTO api_tool_headers (api_tool_id, header_key, header_value)
                VALUES (%s, %s, %s)
            """
            for key, value in headers.items():
                db.execute(header_query, (tool_id, key, str(value)))
        tool["headers"] = headers
    
    # Update params
    if params is not None:
        db.execute("DELETE FROM api_tool_params WHERE api_tool_id = %s", (tool_id,))
        if params:
            param_query = """
                INSERT INTO api_tool_params (api_tool_id, param_key, param_value, param_type)
                VALUES (%s, %s, %s, %s)
            """
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
                
                db.execute(param_query, (tool_id, key, str(value) if value is not None else None, param_type))
        tool["params"] = params
    
    # Update body_schema
    if body_schema is not None:
        db.execute("DELETE FROM api_tool_body_fields WHERE api_tool_id = %s", (tool_id,))
        if body_schema:
            field_query = """
                INSERT INTO api_tool_body_fields (api_tool_id, field_name, field_type, is_required, description)
                VALUES (%s, %s, %s, %s, %s)
            """
            for field_name, field_info in body_schema.items():
                if isinstance(field_info, dict):
                    field_type = field_info.get("type", "string")
                    is_required = field_info.get("required", False)
                    field_desc = field_info.get("description", "")
                else:
                    field_type = "string"
                    is_required = False
                    field_desc = ""
                
                db.execute(field_query, (tool_id, field_name, field_type, is_required, field_desc))
        tool["body_schema"] = body_schema
    
    # Fetch missing data if not updated
    if headers is None:
        header_query = "SELECT * FROM api_tool_headers WHERE api_tool_id = %s"
        header_rows = db.fetch_all(header_query, (tool_id,))
        tool["headers"] = _build_headers_dict(header_rows)
    
    if params is None:
        param_query = "SELECT * FROM api_tool_params WHERE api_tool_id = %s"
        param_rows = db.fetch_all(param_query, (tool_id,))
        tool["params"] = _build_params_dict(param_rows)
    
    if body_schema is None:
        field_query = "SELECT * FROM api_tool_body_fields WHERE api_tool_id = %s"
        field_rows = db.fetch_all(field_query, (tool_id,))
        tool["body_schema"] = _build_body_schema_dict(field_rows)
    
    return tool


def delete_api_tool_for_owner(
    db: DatabaseSession,
    *,
    tool_id: int,
    owner_id: int,
) -> bool:
    query = """
        DELETE FROM api_tools
        USING workspaces
        WHERE api_tools.workspace_id = workspaces.id
          AND api_tools.id = %s
          AND workspaces.owner_id = %s
        RETURNING api_tools.id
    """
    result = db.fetch_one(query, (tool_id, owner_id))
    return result is not None


def get_api_tools_by_ids(
    db: DatabaseSession,
    *,
    workspace_id: int,
    tool_ids: Sequence[int],
) -> list[dict]:
    if not tool_ids:
        return []
    query = """
        SELECT *
        FROM api_tools
        WHERE workspace_id = %s AND id = ANY(%s)
    """
    tools = db.fetch_all(query, (workspace_id, list(tool_ids)))
    
    for tool in tools:
        # Fetch headers
        header_query = "SELECT * FROM api_tool_headers WHERE api_tool_id = %s"
        header_rows = db.fetch_all(header_query, (tool["id"],))
        tool["headers"] = _build_headers_dict(header_rows)
        
        # Fetch params
        param_query = "SELECT * FROM api_tool_params WHERE api_tool_id = %s"
        param_rows = db.fetch_all(param_query, (tool["id"],))
        tool["params"] = _build_params_dict(param_rows)
        
        # Fetch body schema
        field_query = "SELECT * FROM api_tool_body_fields WHERE api_tool_id = %s"
        field_rows = db.fetch_all(field_query, (tool["id"],))
        tool["body_schema"] = _build_body_schema_dict(field_rows)
    
    return tools


# -----------------------------------------------------------------------------
# Documents
# -----------------------------------------------------------------------------
def create_document(
    db: DatabaseSession,
    *,
    workspace_id: int,
    filename: str,
    file_path: str,
    file_size: int,
    file_type: str,
    status: str = "processing",
) -> dict:
    query = """
        INSERT INTO documents (
            workspace_id, filename, file_path, file_size, file_type, status
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
    """
    return db.fetch_one(
        query,
        (workspace_id, filename, file_path, file_size, file_type, status),
    )


def list_documents_for_workspace(db: DatabaseSession, workspace_id: int) -> list[dict]:
    query = """
        SELECT *
        FROM documents
        WHERE workspace_id = %s
        ORDER BY created_at DESC
    """
    return db.fetch_all(query, (workspace_id,))


def get_document_for_owner(
    db: DatabaseSession,
    *,
    document_id: int,
    owner_id: int,
) -> Optional[dict]:
    query = """
        SELECT documents.*
        FROM documents
        JOIN workspaces ON workspaces.id = documents.workspace_id
        WHERE documents.id = %s AND workspaces.owner_id = %s
        LIMIT 1
    """
    return db.fetch_one(query, (document_id, owner_id))


def get_document_for_user(
    db: DatabaseSession,
    *,
    document_id: int,
    user_id: int,
) -> Optional[dict]:
    """Получить документ для пользователя (владелец или участник воркспейса)"""
    query = """
        SELECT documents.*
        FROM documents
        JOIN workspaces ON workspaces.id = documents.workspace_id
        LEFT JOIN workspace_users wu ON wu.workspace_id = workspaces.id AND wu.user_id = %s
        WHERE documents.id = %s
          AND (workspaces.owner_id = %s OR wu.user_id = %s)
        LIMIT 1
    """
    return db.fetch_one(query, (user_id, document_id, user_id, user_id))


def get_document_by_id(db: DatabaseSession, document_id: int) -> Optional[dict]:
    query = "SELECT * FROM documents WHERE id = %s LIMIT 1"
    return db.fetch_one(query, (document_id,))


def list_document_chunk_ids(db: DatabaseSession, document_id: int) -> list[int]:
    query = "SELECT id FROM document_chunks WHERE document_id = %s"
    rows = db.fetch_all(query, (document_id,))
    return [row["id"] for row in rows]


def insert_document_chunk(
    db: DatabaseSession,
    *,
    document_id: int,
    chunk_text: str,
    chunk_index: int,
) -> dict:
    query = """
        INSERT INTO document_chunks (document_id, chunk_text, chunk_index)
        VALUES (%s, %s, %s)
        RETURNING *
    """
    return db.fetch_one(query, (document_id, chunk_text, chunk_index))


def update_document_status(
    db: DatabaseSession,
    *,
    document_id: int,
    status: str,
    processed_at: Optional[datetime] = None,
    error_message: Optional[str] = None,
) -> Optional[dict]:
    query = """
        UPDATE documents
        SET status = %s,
            processed_at = %s,
            error_message = %s
        WHERE id = %s
        RETURNING *
    """
    return db.fetch_one(query, (status, processed_at, error_message, document_id))


# -----------------------------------------------------------------------------
# Chat sessions & messages
# -----------------------------------------------------------------------------
def create_chat_session(
    db: DatabaseSession,
    *,
    bot_id: int,
    user_id: int,
) -> dict:
    query = """
        INSERT INTO chat_sessions (bot_id, user_id)
        VALUES (%s, %s)
        RETURNING *
    """
    return db.fetch_one(query, (bot_id, user_id))


def get_chat_session_for_user(
    db: DatabaseSession,
    *,
    session_id: int,
    user_id: int,
    bot_id: Optional[int] = None,
) -> Optional[dict]:
    query = """
        SELECT *
        FROM chat_sessions
        WHERE id = %s AND user_id = %s
    """
    params: List[Any] = [session_id, user_id]
    if bot_id is not None:
        query += " AND bot_id = %s"
        params.append(bot_id)
    query += " LIMIT 1"
    return db.fetch_one(query, tuple(params))


def list_chat_sessions_for_user(
    db: DatabaseSession,
    *,
    user_id: int,
    bot_id: Optional[int] = None,
) -> list[dict]:
    query = """
        SELECT *
        FROM chat_sessions
        WHERE user_id = %s
    """
    params: List[Any] = [user_id]
    if bot_id is not None:
        query += " AND bot_id = %s"
        params.append(bot_id)
    query += " ORDER BY last_activity_at DESC, created_at DESC"
    return db.fetch_all(query, tuple(params))


def insert_chat_message(
    db: DatabaseSession,
    *,
    session_id: int,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> dict:
    query = "SELECT * FROM create_chat_message(%s, %s, %s, %s)"
    import json
    # Filter out None values from metadata before sending to DB
    filtered_metadata = None
    if metadata:
        filtered_metadata = {k: v for k, v in metadata.items() if v is not None}
        if not filtered_metadata:  # If all values were None, set to None
            filtered_metadata = None
    
    message = db.fetch_one(query, (session_id, role, content, json.dumps(filtered_metadata) if filtered_metadata else None))
    
    if message and metadata:
        message["message_metadata"] = metadata
    
    return message


def list_messages_for_session(db: DatabaseSession, session_id: int) -> list[dict]:
    query = """
        SELECT *
        FROM chat_messages
        WHERE session_id = %s
        ORDER BY created_at ASC
    """
    messages = db.fetch_all(query, (session_id,))
    
    # Fetch metadata for each message
    for message in messages:
        metadata_query = "SELECT * FROM chat_message_metadata WHERE message_id = %s"
        metadata_rows = db.fetch_all(metadata_query, (message["id"],))
        message["message_metadata"] = _build_metadata_dict(metadata_rows)
    
    return messages


# -----------------------------------------------------------------------------
# Audit Logs
# -----------------------------------------------------------------------------
def list_audit_logs(
    db: DatabaseSession,
    *,
    user_id: Optional[int] = None,
    table_name: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Получить список логов аудита с фильтрацией"""
    query = """
        SELECT 
            al.*,
            u.email as user_email,
            u.full_name as user_name
        FROM audit_logs al
        LEFT JOIN users u ON u.id = al.user_id
        WHERE 1=1
    """
    params: List[Any] = []
    
    if user_id:
        query += " AND al.user_id = %s"
        params.append(user_id)
    
    if table_name:
        query += " AND al.table_name = %s"
        params.append(table_name)
    
    if action:
        query += " AND al.action = %s"
        params.append(action)
    
    query += " ORDER BY al.created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    return db.fetch_all(query, tuple(params))


def get_audit_log_by_id(db: DatabaseSession, log_id: int) -> Optional[dict]:
    """Получить лог аудита по ID"""
    query = """
        SELECT 
            al.*,
            u.email as user_email,
            u.full_name as user_name
        FROM audit_logs al
        LEFT JOIN users u ON u.id = al.user_id
        WHERE al.id = %s
        LIMIT 1
    """
    return db.fetch_one(query, (log_id,))


def count_audit_logs(
    db: DatabaseSession,
    *,
    user_id: Optional[int] = None,
    table_name: Optional[str] = None,
    action: Optional[str] = None,
) -> int:
    """Подсчитать количество логов аудита с фильтрацией"""
    query = "SELECT COUNT(*) as count FROM audit_logs WHERE 1=1"
    params: List[Any] = []
    
    if user_id:
        query += " AND user_id = %s"
        params.append(user_id)
    
    if table_name:
        query += " AND table_name = %s"
        params.append(table_name)
    
    if action:
        query += " AND action = %s"
        params.append(action)
    
    result = db.fetch_one(query, tuple(params))
    return result["count"] if result else 0

