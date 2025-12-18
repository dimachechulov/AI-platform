import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.db import repositories as repo
from app.db.database import DatabaseSession, get_db
from app.services.langchain_service import langchain_service

router = APIRouter()


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
    # Проверка доступа к боту
    bot = repo.get_bot_for_user(db, bot_id=chat_data.bot_id, user_id=current_user["id"])
    
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found"
        )
    
    # Валидация длины сообщения
    if len(chat_data.message) > 2048:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message exceeds 2048 characters"
        )
    
    # Получение или создание сессии
    if chat_data.session_id:
        session = repo.get_chat_session_for_user(
            db,
            session_id=chat_data.session_id,
            user_id=current_user["id"],
            bot_id=chat_data.bot_id,
        )
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found"
            )
    else:
        session = repo.create_chat_session(
            db,
            bot_id=chat_data.bot_id,
            user_id=current_user["id"],
        )
        db.commit()
    
    # Сохранение сообщения пользователя
    repo.insert_chat_message(
        db,
        session_id=session["id"],
        role="user",
        content=chat_data.message,
    )
    db.commit()
    
    # Получение истории сообщений
    history_messages = repo.list_messages_for_session(db, session["id"])
    
    history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in history_messages[:-1] ]
    
    # Обработка через LangChain
    try:
        response_text = await langchain_service.process_message(
            message=chat_data.message,
            history=history,
            bot_config=bot["config"],
            system_prompt=bot["system_prompt"],
            db=db,
            workspace_id=bot["workspace_id"]
        )
        
        # Сохранение ответа бота
        assistant_message = repo.insert_chat_message(
            db,
            session_id=session["id"],
            role="assistant",
            content=response_text,
            metadata={"tokens_used": None}
        )
        db.commit()
        
        return {
            "session_id": session["id"],
            "message": ChatMessageResponse.from_chat_message(assistant_message),
            "metadata": assistant_message.get("message_metadata"),
        }
        
    except Exception as e:
        # Сохранение сообщения об ошибке
        repo.insert_chat_message(
            db,
            session_id=session["id"],
            role="assistant",
            content=f"Error: {str(e)}",
            metadata={"error": True},
        )
        db.commit()
        raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_chat_messages(
    session_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение истории сообщений сессии"""
    session = repo.get_chat_session_for_user(
        db,
        session_id=session_id,
        user_id=current_user["id"],
    )
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )
    
    messages = repo.list_messages_for_session(db, session_id)
    
    return [ChatMessageResponse.from_chat_message(msg) for msg in messages]


@router.get("/sessions", response_model=List[dict])
async def get_chat_sessions(
    bot_id: Optional[int] = None,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка сессий чата"""
    sessions = repo.list_chat_sessions_for_user(
        db,
        user_id=current_user["id"],
        bot_id=bot_id,
    )
    
    return [
        {
            "id": s["id"],
            "bot_id": s["bot_id"],
            "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
        }
        for s in sessions
    ]

