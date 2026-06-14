from __future__ import annotations

import ast
import json
from decimal import Decimal
from typing import Any, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m


def user_to_dict(row: m.User) -> dict:
    return {
        "id": row.id,
        "email": row.email,
        "hashed_password": row.hashed_password,
        "full_name": row.full_name,
        "is_active": row.is_active,
        "created_at": row.created_at,
    }


def workspace_to_dict(row: m.Workspace) -> dict:
    return {"id": row.id, "name": row.name, "owner_id": row.owner_id, "created_at": row.created_at}


def workspace_billing_to_dict(row: m.WorkspaceBilling) -> dict:
    return {
        "workspace_id": row.workspace_id,
        "plan": row.plan,
        "subscription_status": row.subscription_status,
        "stripe_customer_id": row.stripe_customer_id,
        "stripe_subscription_id": row.stripe_subscription_id,
        "stripe_price_id": row.stripe_price_id,
        "current_period_end": row.current_period_end,
        "trial_started_at": row.trial_started_at,
        "trial_ends_at": row.trial_ends_at,
        "balance_usd": Decimal(row.balance_usd),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def billing_transaction_to_dict(row: m.BillingTransaction) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "transaction_type": row.transaction_type,
        "amount_usd": Decimal(row.amount_usd),
        "description": row.description,
        "related_message_id": row.related_message_id,
        "stripe_event_id": row.stripe_event_id,
        "metadata_json": row.metadata_json,
        "created_at": row.created_at,
    }


def document_to_dict(doc: m.Document) -> dict:
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


def build_metadata_dict(rows: list[m.ChatMessageMetadata]) -> dict:
    return {row.metadata_key: row.metadata_value for row in rows}


def normalize_bot_response(bot: dict) -> dict:
    if bot and "temperature" in bot:
        temperature = bot["temperature"]
        if isinstance(temperature, Decimal):
            bot["temperature"] = str(float(temperature))
        elif hasattr(temperature, "__float__"):
            bot["temperature"] = str(float(temperature))
        else:
            bot["temperature"] = str(temperature)
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


def build_config_dict(config_rows: list[m.BotConfig]) -> dict:
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


def bot_to_dict(bot: m.Bot, config_rows: list[m.BotConfig]) -> dict:
    data = {
        "id": bot.id,
        "name": bot.name,
        "workspace_id": bot.workspace_id,
        "system_prompt": bot.system_prompt,
        "temperature": bot.temperature,
        "max_tokens": bot.max_tokens,
        "created_at": bot.created_at,
        "updated_at": bot.updated_at,
        "config": build_config_dict(config_rows),
    }
    return normalize_bot_response(data)


def load_bot_configs(db: Session, bot_id: int) -> list[m.BotConfig]:
    return list(db.scalars(select(m.BotConfig).where(m.BotConfig.bot_id == bot_id)).all())


def build_headers_dict(rows: list[m.ApiToolHeader]) -> dict:
    return {row.header_key: row.header_value for row in rows}


def build_params_dict(rows: list[m.ApiToolParam]) -> dict:
    params: dict = {}
    for row in rows:
        key = row.param_key
        value = row.param_value
        param_type = row.param_type
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


def build_body_schema_dict(rows: list[m.ApiToolBodyField]) -> dict:
    schema: dict = {}
    for row in rows:
        if row.parent_field_id is None:
            field_info: dict = {"type": row.field_type, "required": row.is_required}
            if row.description:
                field_info["description"] = row.description
            schema[row.field_name] = field_info
    return schema


def api_tool_to_dict(
    tool: m.ApiTool,
    headers: list[m.ApiToolHeader],
    params: list[m.ApiToolParam],
    body_fields: list[m.ApiToolBodyField],
) -> dict:
    return {
        "id": tool.id,
        "workspace_id": tool.workspace_id,
        "name": tool.name,
        "description": tool.description,
        "url": tool.url,
        "method": tool.method,
        "created_at": tool.created_at,
        "headers": build_headers_dict(headers),
        "params": build_params_dict(params),
        "body_schema": build_body_schema_dict(body_fields),
    }


def load_api_tool_parts(
    db: Session,
    tool_id: int,
) -> tuple[list[m.ApiToolHeader], list[m.ApiToolParam], list[m.ApiToolBodyField]]:
    headers = list(db.scalars(select(m.ApiToolHeader).where(m.ApiToolHeader.api_tool_id == tool_id)).all())
    params = list(db.scalars(select(m.ApiToolParam).where(m.ApiToolParam.api_tool_id == tool_id)).all())
    fields = list(db.scalars(select(m.ApiToolBodyField).where(m.ApiToolBodyField.api_tool_id == tool_id)).all())
    return headers, params, fields


TOKEN_USAGE_PER_MSG_CTE = """
WITH per_msg AS (
  SELECT
    cm.id AS message_id,
    cm.created_at,
    s.bot_id,
    COALESCE(
      MAX(
        CASE
          WHEN cmm.metadata_key = 'input_tokens' AND cmm.metadata_value ~ '^[0-9]+$'
          THEN cmm.metadata_value::bigint
        END
      ),
      0
    )::bigint AS input_tokens,
    COALESCE(
      MAX(
        CASE
          WHEN cmm.metadata_key = 'output_tokens' AND cmm.metadata_value ~ '^[0-9]+$'
          THEN cmm.metadata_value::bigint
        END
      ),
      0
    )::bigint AS output_tokens,
    MAX(CASE WHEN cmm.metadata_key = 'model' THEN cmm.metadata_value END) AS model_name
  FROM chat_messages cm
  INNER JOIN chat_sessions s ON s.id = cm.session_id
  INNER JOIN bots b ON b.id = s.bot_id
  LEFT JOIN chat_message_metadata cmm ON cmm.message_id = cm.id
  WHERE cm.role = 'assistant'
    AND s.user_id = :user_id
    AND b.workspace_id = :workspace_id
    AND cm.created_at >= :time_from AND cm.created_at < :time_to
  GROUP BY cm.id, cm.created_at, s.bot_id
),
filtered AS (
  SELECT *
  FROM per_msg
  WHERE (input_tokens > 0 OR output_tokens > 0)
    AND (:bot_id IS NULL OR bot_id = :bot_id)
    AND (:model IS NULL OR model_name = :model)
)
"""


TOKEN_USAGE_MODEL_LIST_CTE = """
WITH per_msg AS (
  SELECT
    cm.id AS message_id,
    cm.created_at,
    s.bot_id,
    COALESCE(
      MAX(
        CASE
          WHEN cmm.metadata_key = 'input_tokens' AND cmm.metadata_value ~ '^[0-9]+$'
          THEN cmm.metadata_value::bigint
        END
      ),
      0
    )::bigint AS input_tokens,
    COALESCE(
      MAX(
        CASE
          WHEN cmm.metadata_key = 'output_tokens' AND cmm.metadata_value ~ '^[0-9]+$'
          THEN cmm.metadata_value::bigint
        END
      ),
      0
    )::bigint AS output_tokens,
    MAX(CASE WHEN cmm.metadata_key = 'model' THEN cmm.metadata_value END) AS model_name
  FROM chat_messages cm
  INNER JOIN chat_sessions s ON s.id = cm.session_id
  INNER JOIN bots b ON b.id = s.bot_id
  LEFT JOIN chat_message_metadata cmm ON cmm.message_id = cm.id
  WHERE cm.role = 'assistant'
    AND s.user_id = :user_id
    AND b.workspace_id = :workspace_id
    AND cm.created_at >= :time_from AND cm.created_at < :time_to
  GROUP BY cm.id, cm.created_at, s.bot_id
),
with_usage AS (
  SELECT *
  FROM per_msg
  WHERE (input_tokens > 0 OR output_tokens > 0)
    AND (:bot_id IS NULL OR bot_id = :bot_id)
)
"""
