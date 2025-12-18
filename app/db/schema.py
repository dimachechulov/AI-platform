"""
Database schema definition expressed as raw SQL statements.

Used by deployment scripts to provision the database without Alembic.
"""
from __future__ import annotations

SCHEMA_STATEMENTS: list[str] = [
    # ENUM types
    """
    DO $$ BEGIN
        CREATE TYPE http_method AS ENUM ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE document_status AS ENUM ('pending', 'processing', 'processed', 'failed');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE file_type AS ENUM ('txt', 'pdf', 'doc', 'docx', 'md', 'html', 'json', 'csv', 'xml');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$;
    """,
    
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
    CREATE TABLE IF NOT EXISTS workspace_users (
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL DEFAULT 'member',
        added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (workspace_id, user_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS bots (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        system_prompt TEXT NOT NULL,
        temperature NUMERIC(3, 2) NOT NULL DEFAULT 0.7 CHECK (temperature >= 0 AND temperature <= 2),
        max_tokens INTEGER NOT NULL DEFAULT 2048 CHECK (max_tokens > 0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS bot_config (
        id SERIAL PRIMARY KEY,
        bot_id INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        config_key TEXT NOT NULL,
        config_value TEXT NOT NULL,
        value_type TEXT NOT NULL DEFAULT 'string' CHECK (value_type IN ('string', 'number', 'boolean', 'array', 'object')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ,
        UNIQUE (bot_id, config_key)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_size INTEGER NOT NULL CHECK (file_size >= 0),
        file_type file_type NOT NULL,
        status document_status NOT NULL DEFAULT 'processing',
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
        chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
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
        method http_method NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS api_tool_headers (
        id SERIAL PRIMARY KEY,
        api_tool_id INTEGER NOT NULL REFERENCES api_tools(id) ON DELETE CASCADE,
        header_key TEXT NOT NULL,
        header_value TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (api_tool_id, header_key)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS api_tool_params (
        id SERIAL PRIMARY KEY,
        api_tool_id INTEGER NOT NULL REFERENCES api_tools(id) ON DELETE CASCADE,
        param_key TEXT NOT NULL,
        param_value TEXT,
        param_type TEXT NOT NULL DEFAULT 'string' CHECK (param_type IN ('string', 'number', 'boolean', 'array')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (api_tool_id, param_key)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS api_tool_body_fields (
        id SERIAL PRIMARY KEY,
        api_tool_id INTEGER NOT NULL REFERENCES api_tools(id) ON DELETE CASCADE,
        field_name TEXT NOT NULL,
        field_type TEXT NOT NULL DEFAULT 'string' CHECK (field_type IN ('string', 'number', 'boolean', 'array', 'object', 'null')),
        is_required BOOLEAN NOT NULL DEFAULT FALSE,
        description TEXT,
        parent_field_id INTEGER REFERENCES api_tool_body_fields(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (api_tool_id, field_name, parent_field_id)
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
        role message_role NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_message_metadata (
        id SERIAL PRIMARY KEY,
        message_id INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
        metadata_key TEXT NOT NULL,
        metadata_value TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (message_id, metadata_key)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_chunk_embeddings (
        chunk_id INTEGER PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE,
        workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        embedding vector(768) NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_chunk_metadata (
        id SERIAL PRIMARY KEY,
        chunk_id INTEGER NOT NULL REFERENCES document_chunk_embeddings(chunk_id) ON DELETE CASCADE,
        metadata_key TEXT NOT NULL,
        metadata_value TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (chunk_id, metadata_key)
    );
    """,
    """
    ALTER TABLE IF EXISTS chat_sessions
        ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    """,
    """
    ALTER TABLE IF EXISTS chat_sessions
        ADD COLUMN IF NOT EXISTS message_count INTEGER NOT NULL DEFAULT 0 CHECK (message_count >= 0);
    """,
    """
    CREATE OR REPLACE FUNCTION create_chat_message(
        p_session_id INTEGER,
        p_role TEXT,
        p_content TEXT,
        p_metadata JSON DEFAULT NULL
    )
    RETURNS chat_messages
    LANGUAGE plpgsql
    AS $$
    DECLARE
        result chat_messages;
        v_key TEXT;
        v_value TEXT;
    BEGIN
        INSERT INTO chat_messages (session_id, role, content)
        VALUES (p_session_id, p_role::message_role, p_content)
        RETURNING * INTO result;
        
        IF p_metadata IS NOT NULL THEN
            FOR v_key, v_value IN SELECT * FROM json_each_text(p_metadata)
            LOOP
                -- Skip NULL values as metadata_value is NOT NULL
                IF v_value IS NOT NULL THEN
                    INSERT INTO chat_message_metadata (message_id, metadata_key, metadata_value)
                    VALUES (result.id, v_key, v_value);
                END IF;
            END LOOP;
        END IF;

        UPDATE chat_sessions
        SET last_activity_at = COALESCE(result.created_at, NOW()),
            message_count = message_count + 1
        WHERE id = p_session_id;

        RETURN result;
    END;
    $$;
    """,
    """
    CREATE OR REPLACE FUNCTION trg_bots_set_updated_at()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$;
    """,
    """
    DROP TRIGGER IF EXISTS trg_bots_set_updated_at ON bots;
    CREATE TRIGGER trg_bots_set_updated_at
    BEFORE UPDATE ON bots
    FOR EACH ROW
    EXECUTE FUNCTION trg_bots_set_updated_at();
    """,
    """
    CREATE OR REPLACE FUNCTION trg_bot_config_set_updated_at()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$;
    """,
    """
    DROP TRIGGER IF EXISTS trg_bot_config_set_updated_at ON bot_config;
    CREATE TRIGGER trg_bot_config_set_updated_at
    BEFORE UPDATE ON bot_config
    FOR EACH ROW
    EXECUTE FUNCTION trg_bot_config_set_updated_at();
    """,
    """
    CREATE OR REPLACE FUNCTION trg_documents_set_processed_at()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        IF NEW.status = 'processed'::document_status THEN
            NEW.processed_at := COALESCE(NEW.processed_at, NOW());
        ELSE
            NEW.processed_at := NULL;
        END IF;
        RETURN NEW;
    END;
    $$;
    """,
    """
    DROP TRIGGER IF EXISTS trg_documents_set_processed_at ON documents;
    CREATE TRIGGER trg_documents_set_processed_at
    BEFORE INSERT OR UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION trg_documents_set_processed_at();
    """,
    
    # Audit logging
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        action TEXT NOT NULL,
        table_name TEXT NOT NULL,
        record_id INTEGER,
        old_data JSONB,
        new_data JSONB,
        ip_address TEXT,
        user_agent TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE OR REPLACE FUNCTION audit_trigger_function()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    DECLARE
        v_user_id INTEGER;
        v_action TEXT;
        v_old_data JSONB;
        v_new_data JSONB;
        v_record_id INTEGER;
    BEGIN
        -- Determine action type
        IF TG_OP = 'INSERT' THEN
            v_action := 'INSERT';
            v_new_data := to_jsonb(NEW);
            v_old_data := NULL;
        ELSIF TG_OP = 'UPDATE' THEN
            v_action := 'UPDATE';
            v_old_data := to_jsonb(OLD);
            v_new_data := to_jsonb(NEW);
        ELSIF TG_OP = 'DELETE' THEN
            v_action := 'DELETE';
            v_old_data := to_jsonb(OLD);
            v_new_data := NULL;
        END IF;
        
        -- Try to get user_id from session variable
        BEGIN
            v_user_id := current_setting('app.user_id', TRUE)::INTEGER;
        EXCEPTION
            WHEN OTHERS THEN
                v_user_id := NULL;
        END;
        
        -- Get record_id - handle tables with different primary key structures
        BEGIN
            IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
                v_record_id := (NEW).id;
            ELSE
                v_record_id := (OLD).id;
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                -- Table doesn't have 'id' field (e.g., workspace_users)
                v_record_id := NULL;
        END;
        
        INSERT INTO audit_logs (
            user_id,
            action,
            table_name,
            record_id,
            old_data,
            new_data,
            created_at
        ) VALUES (
            v_user_id,
            v_action,
            TG_TABLE_NAME,
            v_record_id,
            v_old_data,
            v_new_data,
            NOW()
        );
        
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END;
    $$;
    """,
    """
    DROP TRIGGER IF EXISTS audit_trigger_bots ON bots;
    CREATE TRIGGER audit_trigger_bots
    AFTER INSERT OR UPDATE OR DELETE ON bots
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();
    """,
    """
    DROP TRIGGER IF EXISTS audit_trigger_api_tools ON api_tools;
    CREATE TRIGGER audit_trigger_api_tools
    AFTER INSERT OR UPDATE OR DELETE ON api_tools
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();
    """,
    """
    DROP TRIGGER IF EXISTS audit_trigger_documents ON documents;
    CREATE TRIGGER audit_trigger_documents
    AFTER INSERT OR UPDATE OR DELETE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();
    """,
    """
    DROP TRIGGER IF EXISTS audit_trigger_workspaces ON workspaces;
    CREATE TRIGGER audit_trigger_workspaces
    AFTER INSERT OR UPDATE OR DELETE ON workspaces
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();
    """,
    """
    DROP TRIGGER IF EXISTS audit_trigger_workspace_users ON workspace_users;
    CREATE TRIGGER audit_trigger_workspace_users
    AFTER INSERT OR UPDATE OR DELETE ON workspace_users
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();
    """,
]

INDEX_STATEMENTS: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces (owner_id);",
    "CREATE INDEX IF NOT EXISTS idx_workspace_users_user ON workspace_users (user_id);",
    "CREATE INDEX IF NOT EXISTS idx_workspace_users_workspace ON workspace_users (workspace_id);",
    "CREATE INDEX IF NOT EXISTS idx_bots_workspace ON bots (workspace_id);",
    "CREATE INDEX IF NOT EXISTS idx_bot_config_bot ON bot_config (bot_id);",
    "CREATE INDEX IF NOT EXISTS idx_bot_config_key ON bot_config (bot_id, config_key);",
    "CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents (workspace_id);",
    "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status);",
    "CREATE INDEX IF NOT EXISTS idx_documents_file_type ON documents (file_type);",
    "CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks (document_id);",
    "CREATE INDEX IF NOT EXISTS idx_api_tools_workspace ON api_tools (workspace_id);",
    "CREATE INDEX IF NOT EXISTS idx_api_tools_method ON api_tools (method);",
    "CREATE INDEX IF NOT EXISTS idx_api_tool_headers_tool ON api_tool_headers (api_tool_id);",
    "CREATE INDEX IF NOT EXISTS idx_api_tool_params_tool ON api_tool_params (api_tool_id);",
    "CREATE INDEX IF NOT EXISTS idx_api_tool_body_fields_tool ON api_tool_body_fields (api_tool_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions (user_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_bot ON chat_sessions (bot_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages (session_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_role ON chat_messages (role);",
    "CREATE INDEX IF NOT EXISTS idx_chat_message_metadata_message ON chat_message_metadata (message_id);",
    "CREATE INDEX IF NOT EXISTS idx_embeddings_workspace ON document_chunk_embeddings (workspace_id);",
    "CREATE INDEX IF NOT EXISTS idx_chunk_metadata_chunk ON document_chunk_metadata (chunk_id);",
    """
    CREATE INDEX IF NOT EXISTS idx_embeddings_cosine
    ON document_chunk_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs (user_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_table ON audit_logs (table_name);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at DESC);",
]


def apply_schema(connection) -> None:
    """Execute schema statements using the provided psycopg2 connection."""
    with connection.cursor() as cursor:
        for statement in SCHEMA_STATEMENTS + INDEX_STATEMENTS:
            cursor.execute(statement)
    connection.commit()

