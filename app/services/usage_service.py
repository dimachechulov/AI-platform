from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException, status

from app.db.database import DatabaseSession
from app.db.usage_repository import UsageRepository

MAX_RANGE_HOURS = 24 * 30
DEFAULT_RANGE_HOURS = 3
DEFAULT_BUCKET_MINUTES = 10


class UsageService:
    def __init__(self, repository: UsageRepository):
        self.repository = repository

    def get_token_usage(
        self,
        db: DatabaseSession,
        *,
        user_id: int,
        workspace_id: int,
        time_from: Optional[datetime],
        time_to: Optional[datetime],
        bucket_minutes: int,
        bot_id: Optional[int],
        model: Optional[str],
    ) -> dict:
        now = datetime.now(timezone.utc)
        t_to = self._utc(time_to) if time_to else now
        t_from = self._utc(time_from) if time_from else t_to - timedelta(hours=DEFAULT_RANGE_HOURS)
        self._validate_range(t_from, t_to)
        self._validate_bot_access(db, user_id=user_id, workspace_id=workspace_id, bot_id=bot_id)

        totals = self.repository.get_token_usage_totals(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            time_from=t_from,
            time_to=t_to,
            bot_id=bot_id,
            model=model,
        )
        raw_buckets = self.repository.get_token_usage_buckets(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            time_from=t_from,
            time_to=t_to,
            bucket_minutes=bucket_minutes,
            bot_id=bot_id,
            model=model,
        )
        filled = self._fill_time_buckets(t_from, t_to, bucket_minutes, raw_buckets)
        return {
            "workspace_id": workspace_id,
            "time_from": t_from,
            "time_to": t_to,
            "bucket_minutes": bucket_minutes,
            "bot_id": bot_id,
            "model": model,
            "totals": totals,
            "buckets": filled,
        }

    def list_token_usage_models(
        self,
        db: DatabaseSession,
        *,
        user_id: int,
        workspace_id: int,
        time_from: Optional[datetime],
        time_to: Optional[datetime],
        bot_id: Optional[int],
    ) -> list[str]:
        now = datetime.now(timezone.utc)
        t_to = self._utc(time_to) if time_to else now
        t_from = self._utc(time_from) if time_from else t_to - timedelta(hours=DEFAULT_RANGE_HOURS)
        self._validate_bot_access(db, user_id=user_id, workspace_id=workspace_id, bot_id=bot_id)
        return self.repository.list_distinct_models_for_token_usage(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            time_from=t_from,
            time_to=t_to,
            bot_id=bot_id,
        )

    @staticmethod
    def _utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    def _align_bucket_start(cls, dt: datetime, bucket_minutes: int) -> datetime:
        dt = cls._utc(dt).replace(second=0, microsecond=0)
        hour_floor = dt.replace(minute=0)
        minutes = (dt.minute // bucket_minutes) * bucket_minutes
        return hour_floor + timedelta(minutes=minutes)

    @classmethod
    def _fill_time_buckets(
        cls,
        time_from: datetime,
        time_to: datetime,
        bucket_minutes: int,
        rows: List[dict],
    ) -> List[dict]:
        row_by_start: dict[datetime, dict] = {}
        for row in rows:
            key = cls._align_bucket_start(row["bucket_start"], bucket_minutes)
            row_by_start[key] = row

        out: List[dict] = []
        cur = cls._align_bucket_start(time_from, bucket_minutes)
        delta = timedelta(minutes=bucket_minutes)
        while cur < time_to:
            nxt = cur + delta
            row = row_by_start.get(cur)
            out.append(
                {
                    "bucket_start": cur,
                    "bucket_end": nxt,
                    "input_tokens": row["input_tokens"] if row else 0,
                    "output_tokens": row["output_tokens"] if row else 0,
                }
            )
            cur = nxt
        return out

    @staticmethod
    def _validate_range(time_from: datetime, time_to: datetime) -> None:
        if time_from >= time_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="time_from must be before time_to",
            )
        if (time_to - time_from).total_seconds() > MAX_RANGE_HOURS * 3600:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Period must not exceed {MAX_RANGE_HOURS} hours",
            )

    def _validate_bot_access(
        self,
        db: DatabaseSession,
        *,
        user_id: int,
        workspace_id: int,
        bot_id: Optional[int],
    ) -> None:
        if bot_id is None:
            return
        bot = self.repository.get_bot_for_user(db, bot_id=bot_id, user_id=user_id)
        if bot and bot["workspace_id"] == workspace_id:
            return
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found in this workspace",
        )
