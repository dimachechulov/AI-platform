from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session, aliased

from app.db import models as m
from app.db.repository_utils import (
    TOKEN_USAGE_MODEL_LIST_CTE,
    TOKEN_USAGE_PER_MSG_CTE,
    bot_to_dict,
    load_bot_configs,
)


class UsageRepository:
    def get_bot_for_user(self, db: Session, *, bot_id: int, user_id: int) -> Optional[dict]:
        workspace_user = aliased(m.WorkspaceUser)
        bot = db.scalars(
            select(m.Bot)
            .join(m.Workspace, m.Workspace.id == m.Bot.workspace_id)
            .outerjoin(workspace_user, and_(workspace_user.workspace_id == m.Workspace.id, workspace_user.user_id == user_id))
            .where(m.Bot.id == bot_id)
            .where(or_(m.Workspace.owner_id == user_id, workspace_user.user_id == user_id))
        ).first()
        if not bot:
            return None
        return bot_to_dict(bot, load_bot_configs(db, bot.id))

    def get_token_usage_totals(
        self,
        db: Session,
        *,
        user_id: int,
        workspace_id: int,
        time_from: datetime,
        time_to: datetime,
        bot_id: Optional[int],
        model: Optional[str],
    ) -> Dict[str, int]:
        sql = text(
            TOKEN_USAGE_PER_MSG_CTE
            + """
SELECT COALESCE(SUM(input_tokens), 0)::bigint AS input_tokens,
       COALESCE(SUM(output_tokens), 0)::bigint AS output_tokens
FROM filtered
"""
        )
        row = db.execute(
            sql,
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "time_from": time_from,
                "time_to": time_to,
                "bot_id": bot_id,
                "model": model,
            },
        ).mappings().one()
        return {"input_tokens": int(row["input_tokens"]), "output_tokens": int(row["output_tokens"])}

    def get_token_usage_buckets(
        self,
        db: Session,
        *,
        user_id: int,
        workspace_id: int,
        time_from: datetime,
        time_to: datetime,
        bucket_minutes: int,
        bot_id: Optional[int],
        model: Optional[str],
    ) -> List[Dict[str, Any]]:
        sql = text(
            TOKEN_USAGE_PER_MSG_CTE
            + """
, bucketed AS (
  SELECT
    date_trunc('hour', created_at)
      + (floor(extract(minute from created_at) / :bucket_minutes) * :bucket_minutes)
      * interval '1 minute' AS bucket_start,
    input_tokens,
    output_tokens
  FROM filtered
)
SELECT bucket_start,
       SUM(input_tokens)::bigint AS input_tokens,
       SUM(output_tokens)::bigint AS output_tokens
FROM bucketed
GROUP BY bucket_start
ORDER BY bucket_start
"""
        )
        rows = db.execute(
            sql,
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "time_from": time_from,
                "time_to": time_to,
                "bot_id": bot_id,
                "model": model,
                "bucket_minutes": bucket_minutes,
            },
        ).mappings().all()
        return [
            {
                "bucket_start": row["bucket_start"],
                "input_tokens": int(row["input_tokens"]),
                "output_tokens": int(row["output_tokens"]),
            }
            for row in rows
        ]

    def list_distinct_models_for_token_usage(
        self,
        db: Session,
        *,
        user_id: int,
        workspace_id: int,
        time_from: datetime,
        time_to: datetime,
        bot_id: Optional[int],
    ) -> List[str]:
        sql = text(
            TOKEN_USAGE_MODEL_LIST_CTE
            + """
SELECT DISTINCT model_name
FROM with_usage
WHERE model_name IS NOT NULL
ORDER BY model_name
"""
        )
        rows = db.execute(
            sql,
            {
                "user_id": user_id,
                "workspace_id": workspace_id,
                "time_from": time_from,
                "time_to": time_to,
                "bot_id": bot_id,
            },
        ).all()
        return [row[0] for row in rows if row[0]]
