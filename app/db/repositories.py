from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from psycopg2.extras import Json

from app.db.database import DatabaseSession


def _json(value: Optional[Any]) -> Optional[Json]:
    return Json(value) if value is not None else None


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
    query = """
        INSERT INTO bots (name, workspace_id, system_prompt, config, temperature, max_tokens)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
    """
    return db.fetch_one(
        query,
        (name, workspace_id, system_prompt, _json(config), temperature, max_tokens),
    )


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
    return db.fetch_all(base_query, tuple(params))


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
    return db.fetch_one(query, (bot_id, owner_id))


def get_bot_by_id(db: DatabaseSession, bot_id: int) -> Optional[dict]:
    query = "SELECT * FROM bots WHERE id = %s LIMIT 1"
    return db.fetch_one(query, (bot_id,))


def update_bot_for_owner(
    db: DatabaseSession,
    *,
    bot_id: int,
    owner_id: int,
    updates: Dict[str, Any],
) -> Optional[dict]:
    if not updates:
        return get_bot_for_owner(db, bot_id=bot_id, owner_id=owner_id)

    columns: List[str] = []
    params: List[Any] = []
    for column, value in updates.items():
        if column == "config":
            value = _json(value)
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
    return db.fetch_one(query, tuple(params))


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
    query = """
        INSERT INTO api_tools (
            workspace_id, name, description, url, method, headers, params, body_schema
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
    """
    return db.fetch_one(
        query,
        (
            workspace_id,
            name,
            description,
            url,
            method,
            _json(headers),
            _json(params),
            _json(body_schema),
        ),
    )


def list_api_tools_for_workspace(db: DatabaseSession, workspace_id: int) -> list[dict]:
    query = """
        SELECT *
        FROM api_tools
        WHERE workspace_id = %s
        ORDER BY created_at DESC
    """
    return db.fetch_all(query, (workspace_id,))


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
    return db.fetch_one(query, (tool_id, owner_id))


def update_api_tool_for_owner(
    db: DatabaseSession,
    *,
    tool_id: int,
    owner_id: int,
    updates: Dict[str, Any],
) -> Optional[dict]:
    if not updates:
        return get_api_tool_for_owner(db, tool_id=tool_id, owner_id=owner_id)

    columns: List[str] = []
    params: List[Any] = []
    for column, value in updates.items():
        if column in {"headers", "params", "body_schema"}:
            value = _json(value)
        columns.append(f"{column} = %s")
        params.append(value)

    params.extend([tool_id, owner_id])
    query = f"""
        UPDATE api_tools
        SET {', '.join(columns)}
        FROM workspaces
        WHERE api_tools.workspace_id = workspaces.id
          AND api_tools.id = %s
          AND workspaces.owner_id = %s
        RETURNING api_tools.*
    """
    return db.fetch_one(query, tuple(params))


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
    return db.fetch_all(query, (workspace_id, list(tool_ids)))


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
    query += " ORDER BY created_at DESC"
    return db.fetch_all(query, tuple(params))


def insert_chat_message(
    db: DatabaseSession,
    *,
    session_id: int,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> dict:
    query = """
        INSERT INTO chat_messages (session_id, role, content, message_metadata)
        VALUES (%s, %s, %s, %s)
        RETURNING *
    """
    return db.fetch_one(query, (session_id, role, content, _json(metadata)))


def list_messages_for_session(db: DatabaseSession, session_id: int) -> list[dict]:
    query = """
        SELECT *
        FROM chat_messages
        WHERE session_id = %s
        ORDER BY created_at ASC
    """
    return db.fetch_all(query, (session_id,))

