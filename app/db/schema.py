"""
Database schema definition expressed as raw SQL statements.

Used by deployment scripts to provision the database without Alembic.
"""
from __future__ import annotations

SCHEMA_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        hashed_password TEXT NOT NULL,
        full_name TEXT,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS workspaces (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS bots (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        system_prompt TEXT NOT NULL,
        config JSONB NOT NULL DEFAULT '{}'::jsonb,
        temperature TEXT NOT NULL DEFAULT '0.7',
        max_tokens INTEGER NOT NULL DEFAULT 2048,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        file_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'processing',
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        processed_at TIMESTAMPTZ
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_chunks (
        id SERIAL PRIMARY KEY,
        document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        chunk_text TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        embedding BYTEA,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (document_id, chunk_index)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS api_tools (
        id SERIAL PRIMARY KEY,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT,
        url TEXT NOT NULL,
        method TEXT NOT NULL,
        headers JSONB,
        params JSONB,
        body_schema JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id SERIAL PRIMARY KEY,
        bot_id INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id SERIAL PRIMARY KEY,
        session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        message_metadata JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_chunk_embeddings (
        chunk_id INTEGER PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        metadata JSONB NOT NULL,
        embedding vector(768) NOT NULL
    );
    """,
]

INDEX_STATEMENTS: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces (owner_id);",
    "CREATE INDEX IF NOT EXISTS idx_bots_workspace ON bots (workspace_id);",
    "CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents (workspace_id);",
    "CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks (document_id);",
    "CREATE INDEX IF NOT EXISTS idx_api_tools_workspace ON api_tools (workspace_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions (user_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_bot ON chat_sessions (bot_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages (session_id);",
    "CREATE INDEX IF NOT EXISTS idx_embeddings_workspace ON document_chunk_embeddings (workspace_id);",
    """
    CREATE INDEX IF NOT EXISTS idx_embeddings_cosine
    ON document_chunk_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
    """,
]


def apply_schema(connection) -> None:
    """Execute schema statements using the provided psycopg2 connection."""
    with connection.cursor() as cursor:
        for statement in SCHEMA_STATEMENTS + INDEX_STATEMENTS:
            cursor.execute(statement)
    connection.commit()

