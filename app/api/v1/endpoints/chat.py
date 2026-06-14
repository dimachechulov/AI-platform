import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.db.database import DatabaseSession, get_db
from app.db.chat_repository import ChatRepository
from app.services.chat_service import ChatService
from app.services.plan_guard import enforce_message_limit, enforce_model_allowed, enforce_positive_balance

router = APIRouter()
chat_service = ChatService(ChatRepository())


class ChatMessageRequest(BaseModel):
    message: str
    bot_id: int
    session_id: Optional[int] = None


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    metadata: Optional[dict] = None
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_chat_message(cls, msg: Dict):
        """Создает ChatMessageResponse из ChatMessage, преобразуя message_metadata в metadata"""
        return cls(
            id=msg["id"],
            role=msg["role"],
            content=msg["content"],
            metadata=msg.get("message_metadata"),
            created_at=msg["created_at"]
        )


class ChatResponse(BaseModel):
    session_id: int
    message: ChatMessageResponse
    metadata: dict = None


@router.post("/", response_model=ChatResponse)
async def send_message(
    chat_data: ChatMessageRequest,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    bot = chat_service.repository.get_bot_for_user(db, bot_id=chat_data.bot_id, user_id=current_user["id"])
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )
    enforce_model_allowed(db, bot["workspace_id"], (bot.get("config") or {}).get("gemini_model"))
    enforce_message_limit(db, bot["workspace_id"])
    enforce_positive_balance(db, bot["workspace_id"])
    response = await chat_service.send_message(
        db,
        user_id=current_user["id"],
        bot_id=chat_data.bot_id,
        message=chat_data.message,
        session_id=chat_data.session_id,
    )
    assistant_message = response["assistant_message"]
    return {
        "session_id": response["session_id"],
        "message": ChatMessageResponse.from_chat_message(assistant_message),
        "metadata": assistant_message.get("message_metadata"),
    }


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_chat_messages(
    session_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение истории сообщений сессии"""
    messages = chat_service.list_chat_messages(db, user_id=current_user["id"], session_id=session_id)
    return [ChatMessageResponse.from_chat_message(msg) for msg in messages]


@router.get("/sessions", response_model=List[dict])
async def get_chat_sessions(
    bot_id: Optional[int] = None,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка сессий чата"""
    return chat_service.list_chat_sessions(db, user_id=current_user["id"], bot_id=bot_id)

