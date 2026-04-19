import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user
from app.services.gemini_models_service import list_chat_models_cached

router = APIRouter()


class GeminiChatModelItem(BaseModel):
    name: str = Field(..., description="Идентификатор модели для graph / LangChain (без префикса models/)")
    display_name: str | None = None
    description: str | None = None


@router.get("/chat-models", response_model=List[GeminiChatModelItem])
async def list_gemini_chat_models(
    _current_user: dict = Depends(get_current_user),
):
    """Доступные для ключа приложения чат-модели (generateContent). Список кешируется (lru_cache) до перезапуска."""
    try:
        data = await asyncio.to_thread(list_chat_models_cached)
        return data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
