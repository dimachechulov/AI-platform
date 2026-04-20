from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.dependencies import check_workspace_access, get_current_user
from app.db import repositories as repo
from app.db.database import DatabaseSession, get_db

router = APIRouter()

MAX_RANGE_HOURS = 24 * 30
DEFAULT_RANGE_HOURS = 3
DEFAULT_BUCKET_MINUTES = 10


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _align_bucket_start(dt: datetime, bucket_minutes: int) -> datetime:
    dt = _utc(dt).replace(second=0, microsecond=0)
    hour_floor = dt.replace(minute=0)
    m = (dt.minute // bucket_minutes) * bucket_minutes
    return hour_floor + timedelta(minutes=m)


def _fill_time_buckets(
    time_from: datetime,
    time_to: datetime,
    bucket_minutes: int,
    rows: List[dict],
) -> List[dict]:
    row_by_start: dict[datetime, dict] = {}
    for r in rows:
        bs = r["bucket_start"]
        key = _align_bucket_start(bs, bucket_minutes)
        row_by_start[key] = r

    out: List[dict] = []
    cur = _align_bucket_start(time_from, bucket_minutes)
    delta = timedelta(minutes=bucket_minutes)
    while cur < time_to:
        nxt = cur + delta
        r = row_by_start.get(cur)
        out.append(
            {
                "bucket_start": cur,
                "bucket_end": nxt,
                "input_tokens": r["input_tokens"] if r else 0,
                "output_tokens": r["output_tokens"] if r else 0,
            }
        )
        cur = nxt
    return out


class TokenTotals(BaseModel):
    input_tokens: int
    output_tokens: int


class TokenBucket(BaseModel):
    bucket_start: datetime
    bucket_end: datetime
    input_tokens: int
    output_tokens: int


class TokenUsageResponse(BaseModel):
    workspace_id: int
    time_from: datetime
    time_to: datetime
    bucket_minutes: int
    bot_id: Optional[int] = None
    model: Optional[str] = None
    totals: TokenTotals
    buckets: List[TokenBucket]


class ModelsListResponse(BaseModel):
    models: List[str]


@router.get("/tokens", response_model=TokenUsageResponse)
async def get_token_usage(
    workspace_id: int = Query(..., description="ID рабочего пространства"),
    time_from: Optional[datetime] = Query(
        None, description="Начало периода (UTC). По умолчанию: сейчас − 3 ч"
    ),
    time_to: Optional[datetime] = Query(None, description="Конец периода (UTC). По умолчанию: сейчас"),
    bucket_minutes: int = Query(
        DEFAULT_BUCKET_MINUTES,
        ge=1,
        le=24 * 60,
        description="Длина интервала на графике, минуты",
    ),
    bot_id: Optional[int] = Query(None, description="Только выбранный бот"),
    model: Optional[str] = Query(None, description="Только выбранная модель (точное совпадение)"),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    await check_workspace_access(workspace_id, current_user, db)

    now = datetime.now(timezone.utc)
    t_to = _utc(time_to) if time_to else now
    t_from = _utc(time_from) if time_from else t_to - timedelta(hours=DEFAULT_RANGE_HOURS)

    if t_from >= t_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="time_from must be before time_to",
        )
    if (t_to - t_from).total_seconds() > MAX_RANGE_HOURS * 3600:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Period must not exceed {MAX_RANGE_HOURS} hours",
        )

    if bot_id is not None:
        bot = repo.get_bot_for_user(db, bot_id=bot_id, user_id=current_user["id"])
        if not bot or bot["workspace_id"] != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found in this workspace",
            )

    totals = repo.get_token_usage_totals(
        db,
        user_id=current_user["id"],
        workspace_id=workspace_id,
        time_from=t_from,
        time_to=t_to,
        bot_id=bot_id,
        model=model,
    )
    raw_buckets = repo.get_token_usage_buckets(
        db,
        user_id=current_user["id"],
        workspace_id=workspace_id,
        time_from=t_from,
        time_to=t_to,
        bucket_minutes=bucket_minutes,
        bot_id=bot_id,
        model=model,
    )
    filled = _fill_time_buckets(t_from, t_to, bucket_minutes, raw_buckets)

    return TokenUsageResponse(
        workspace_id=workspace_id,
        time_from=t_from,
        time_to=t_to,
        bucket_minutes=bucket_minutes,
        bot_id=bot_id,
        model=model,
        totals=TokenTotals(**totals),
        buckets=[TokenBucket(**b) for b in filled],
    )


@router.get("/tokens/models", response_model=ModelsListResponse)
async def list_token_usage_models(
    workspace_id: int = Query(...),
    time_from: Optional[datetime] = Query(None),
    time_to: Optional[datetime] = Query(None),
    bot_id: Optional[int] = Query(None),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Список моделей, по которым есть расход токенов в периоде (для выпадающего списка)."""
    await check_workspace_access(workspace_id, current_user, db)

    now = datetime.now(timezone.utc)
    t_to = _utc(time_to) if time_to else now
    t_from = _utc(time_from) if time_from else t_to - timedelta(hours=DEFAULT_RANGE_HOURS)

    if bot_id is not None:
        bot = repo.get_bot_for_user(db, bot_id=bot_id, user_id=current_user["id"])
        if not bot or bot["workspace_id"] != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found in this workspace",
            )

    models = repo.list_distinct_models_for_token_usage(
        db,
        user_id=current_user["id"],
        workspace_id=workspace_id,
        time_from=t_from,
        time_to=t_to,
        bot_id=bot_id,
    )
    return ModelsListResponse(models=models)
