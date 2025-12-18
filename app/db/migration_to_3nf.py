"""
Migration script to normalize database to 3NF.
Removes JSONB fields and creates normalized tables.
"""
from __future__ import annotations

MIGRATION_STATEMENTS: list[str] = [
    # Step 1: Create ENUM types
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
    
    # Step 2: Create new tables for JSONB data
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
    CREATE TABLE IF NOT EXISTS document_chunk_metadata (
        id SERIAL PRIMARY KEY,
        chunk_id INTEGER NOT NULL REFERENCES document_chunk_embeddings(chunk_id) ON DELETE CASCADE,
        metadata_key TEXT NOT NULL,
        metadata_value TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (chunk_id, metadata_key)
    );
    """,
    
    # Step 3: Migrate JSONB data to new tables
    """
    INSERT INTO bot_config (bot_id, config_key, config_value, value_type)
    SELECT 
        id as bot_id,
        key as config_key,
        value::text as config_value,
        CASE jsonb_typeof(value)
            WHEN 'string' THEN 'string'
            WHEN 'number' THEN 'number'
            WHEN 'boolean' THEN 'boolean'
            WHEN 'array' THEN 'array'
            WHEN 'object' THEN 'object'
            ELSE 'string'
        END as value_type
    FROM bots, jsonb_each(config)
    WHERE config IS NOT NULL AND config != '{}'::jsonb
    ON CONFLICT (bot_id, config_key) DO NOTHING;
    """,
    """
    INSERT INTO api_tool_headers (api_tool_id, header_key, header_value)
    SELECT 
        id as api_tool_id,
        key as header_key,
        COALESCE(value::text, '') as header_value
    FROM api_tools, jsonb_each_text(headers)
    WHERE headers IS NOT NULL 
      AND headers != '{}'::jsonb
      AND value IS NOT NULL
    ON CONFLICT (api_tool_id, header_key) DO NOTHING;
    """,
    """
    INSERT INTO api_tool_params (api_tool_id, param_key, param_value, param_type)
    SELECT 
        id as api_tool_id,
        key as param_key,
        value::text as param_value,
        CASE jsonb_typeof(value)
            WHEN 'string' THEN 'string'
            WHEN 'number' THEN 'number'
            WHEN 'boolean' THEN 'boolean'
            WHEN 'array' THEN 'array'
            ELSE 'string'
        END as param_type
    FROM api_tools, jsonb_each(params)
    WHERE params IS NOT NULL AND params != '{}'::jsonb
    ON CONFLICT (api_tool_id, param_key) DO NOTHING;
    """,
    """
    INSERT INTO api_tool_body_fields (api_tool_id, field_name, field_type, description)
    SELECT 
        id as api_tool_id,
        key as field_name,
        CASE jsonb_typeof(value)
            WHEN 'string' THEN 'string'
            WHEN 'number' THEN 'number'
            WHEN 'boolean' THEN 'boolean'
            WHEN 'array' THEN 'array'
            WHEN 'object' THEN 'object'
            ELSE 'string'
        END as field_type,
        COALESCE(value->>'description', '') as description
    FROM api_tools, jsonb_each(body_schema)
    WHERE body_schema IS NOT NULL AND body_schema != '{}'::jsonb
    ON CONFLICT (api_tool_id, field_name, parent_field_id) DO NOTHING;
    """,
    """
    INSERT INTO chat_message_metadata (message_id, metadata_key, metadata_value)
    SELECT 
        id as message_id,
        key as metadata_key,
        COALESCE(value::text, '') as metadata_value
    FROM chat_messages, jsonb_each_text(message_metadata)
    WHERE message_metadata IS NOT NULL 
      AND message_metadata != '{}'::jsonb
      AND value IS NOT NULL
    ON CONFLICT (message_id, metadata_key) DO NOTHING;
    """,
    """
    INSERT INTO document_chunk_metadata (chunk_id, metadata_key, metadata_value)
    SELECT 
        chunk_id,
        key as metadata_key,
        COALESCE(value::text, '') as metadata_value
    FROM document_chunk_embeddings, jsonb_each_text(metadata)
    WHERE metadata IS NOT NULL 
      AND metadata != '{}'::jsonb
      AND value IS NOT NULL
    ON CONFLICT (chunk_id, metadata_key) DO NOTHING;
    """,
    
    # Step 4: Add new enum columns
    """
    ALTER TABLE api_tools 
    ADD COLUMN IF NOT EXISTS method_new http_method;
    """,
    """
    UPDATE api_tools
    SET method_new = UPPER(method)::http_method
    WHERE method_new IS NULL;
    """,
    """
    ALTER TABLE documents 
    ADD COLUMN IF NOT EXISTS status_new document_status;
    """,
    """
    UPDATE documents
    SET status_new = status::document_status
    WHERE status_new IS NULL;
    """,
    """
    UPDATE documents
    SET status_new = 'processing'::document_status
    WHERE status_new IS NULL;
    """,
    """
    ALTER TABLE documents 
    ADD COLUMN IF NOT EXISTS file_type_new file_type;
    """,
    """
    UPDATE documents
    SET file_type_new = file_type::file_type
    WHERE file_type_new IS NULL AND file_type IN ('txt', 'pdf', 'doc', 'docx', 'md', 'html', 'json', 'csv', 'xml');
    """,
    """
    UPDATE documents
    SET file_type_new = 'txt'::file_type
    WHERE file_type_new IS NULL;
    """,
    """
    ALTER TABLE chat_messages 
    ADD COLUMN IF NOT EXISTS role_new message_role;
    """,
    """
    UPDATE chat_messages
    SET role_new = role::message_role
    WHERE role_new IS NULL;
    """,
    
    # Step 5: Fix temperature type
    """
    ALTER TABLE bots ALTER COLUMN temperature DROP DEFAULT;
    """,
    """
    ALTER TABLE bots ALTER COLUMN temperature TYPE NUMERIC(3, 2) 
    USING CASE 
        WHEN temperature ~ '^[0-9]*\\.?[0-9]+$' THEN temperature::NUMERIC(3, 2)
        ELSE 0.7
    END;
    """,
    """
    ALTER TABLE bots ALTER COLUMN temperature SET DEFAULT 0.7;
    """,
    """
    ALTER TABLE bots ADD CONSTRAINT bots_temperature_check 
    CHECK (temperature >= 0 AND temperature <= 2);
    """,
    """
    ALTER TABLE bots ADD CONSTRAINT bots_max_tokens_check 
    CHECK (max_tokens > 0);
    """,
    """
    ALTER TABLE documents ADD CONSTRAINT documents_file_size_check 
    CHECK (file_size >= 0);
    """,
    """
    ALTER TABLE document_chunks ADD CONSTRAINT document_chunks_index_check 
    CHECK (chunk_index >= 0);
    """,
    """
    ALTER TABLE chat_sessions ADD CONSTRAINT chat_sessions_message_count_check 
    CHECK (message_count >= 0);
    """,
    
    # Step 6: Drop old columns and rename new ones
    """
    ALTER TABLE bots DROP COLUMN IF EXISTS config;
    """,
    """
    ALTER TABLE api_tools DROP COLUMN IF EXISTS headers;
    """,
    """
    ALTER TABLE api_tools DROP COLUMN IF EXISTS params;
    """,
    """
    ALTER TABLE api_tools DROP COLUMN IF EXISTS body_schema;
    """,
    """
    ALTER TABLE api_tools DROP COLUMN IF EXISTS method;
    """,
    """
    ALTER TABLE api_tools RENAME COLUMN method_new TO method;
    """,
    """
    ALTER TABLE api_tools ALTER COLUMN method SET NOT NULL;
    """,
    """
    ALTER TABLE chat_messages DROP COLUMN IF EXISTS message_metadata;
    """,
    """
    ALTER TABLE chat_messages DROP COLUMN IF EXISTS role;
    """,
    """
    ALTER TABLE chat_messages RENAME COLUMN role_new TO role;
    """,
    """
    ALTER TABLE chat_messages ALTER COLUMN role SET NOT NULL;
    """,
    """
    ALTER TABLE document_chunk_embeddings DROP COLUMN IF EXISTS metadata;
    """,
    """
    ALTER TABLE documents DROP COLUMN IF EXISTS status;
    """,
    """
    ALTER TABLE documents RENAME COLUMN status_new TO status;
    """,
    """
    ALTER TABLE documents ALTER COLUMN status SET NOT NULL;
    """,
    """
    ALTER TABLE documents DROP COLUMN IF EXISTS file_type;
    """,
    """
    ALTER TABLE documents RENAME COLUMN file_type_new TO file_type;
    """,
    """
    ALTER TABLE documents ALTER COLUMN file_type SET NOT NULL;
    """,
    
    # Step 7: Create indexes
    "CREATE INDEX IF NOT EXISTS idx_bot_config_bot ON bot_config (bot_id);",
    "CREATE INDEX IF NOT EXISTS idx_bot_config_key ON bot_config (bot_id, config_key);",
    "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status);",
    "CREATE INDEX IF NOT EXISTS idx_documents_file_type ON documents (file_type);",
    "CREATE INDEX IF NOT EXISTS idx_api_tools_method ON api_tools (method);",
    "CREATE INDEX IF NOT EXISTS idx_api_tool_headers_tool ON api_tool_headers (api_tool_id);",
    "CREATE INDEX IF NOT EXISTS idx_api_tool_params_tool ON api_tool_params (api_tool_id);",
    "CREATE INDEX IF NOT EXISTS idx_api_tool_body_fields_tool ON api_tool_body_fields (api_tool_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_role ON chat_messages (role);",
    "CREATE INDEX IF NOT EXISTS idx_chat_message_metadata_message ON chat_message_metadata (message_id);",
    "CREATE INDEX IF NOT EXISTS idx_chunk_metadata_chunk ON document_chunk_metadata (chunk_id);",
    
    # Step 8: Update triggers
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
                INSERT INTO chat_message_metadata (message_id, metadata_key, metadata_value)
                VALUES (result.id, v_key, v_value);
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
]


def apply_migration(connection) -> None:
    """Execute migration statements using the provided psycopg2 connection."""
    with connection.cursor() as cursor:
        for i, statement in enumerate(MIGRATION_STATEMENTS, 1):
            try:
                cursor.execute(statement)
                connection.commit()
                print(f"✓ Step {i}/{len(MIGRATION_STATEMENTS)} completed")
            except Exception as e:
                connection.rollback()
                print(f"✗ Step {i}/{len(MIGRATION_STATEMENTS)} failed: {e}")
                print(f"Statement: {statement[:100]}...")
                raise
    print("Migration completed successfully!")


if __name__ == "__main__":
    import psycopg2
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not found in environment")
        exit(1)
    
    print("Connecting to database...")
    conn = psycopg2.connect(db_url)
    
    try:
        print("Starting migration to 3NF...")
        apply_migration(conn)
    finally:
        conn.close()
        print("Database connection closed")
