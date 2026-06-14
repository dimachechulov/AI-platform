from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.dependencies import check_workspace_access, get_current_user
from app.db.database import DatabaseSession, get_db
from app.db.usage_repository import UsageRepository
from app.services.usage_service import DEFAULT_BUCKET_MINUTES, UsageService

router = APIRouter()
usage_service = UsageService(UsageRepository())


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
    usage_data = usage_service.get_token_usage(
        db,
        user_id=current_user["id"],
        workspace_id=workspace_id,
        time_from=time_from,
        time_to=time_to,
        bucket_minutes=bucket_minutes,
        bot_id=bot_id,
        model=model,
    )

    return TokenUsageResponse(
        workspace_id=usage_data["workspace_id"],
        time_from=usage_data["time_from"],
        time_to=usage_data["time_to"],
        bucket_minutes=usage_data["bucket_minutes"],
        bot_id=usage_data["bot_id"],
        model=usage_data["model"],
        totals=TokenTotals(**usage_data["totals"]),
        buckets=[TokenBucket(**b) for b in usage_data["buckets"]],
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
    models = usage_service.list_token_usage_models(
        db,
        user_id=current_user["id"],
        workspace_id=workspace_id,
        time_from=time_from,
        time_to=time_to,
        bot_id=bot_id,
    )
    return ModelsListResponse(models=models)
