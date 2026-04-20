from __future__ import annotations

from fastapi import HTTPException, status

from app.db.database import DatabaseSession
from app.db.chat_repository import ChatRepository
from app.services.billing_service import calculate_llm_cost_usd, normalize_model_name
from app.services.langchain_service import langchain_service


class ChatService:
    def __init__(self, repository: ChatRepository):
        self.repository = repository

    async def send_message(
        self,
        db: DatabaseSession,
        *,
        user_id: int,
        bot_id: int,
        message: str,
        session_id: int | None,
    ) -> dict:
        bot = self.repository.get_bot_for_user(db, bot_id=bot_id, user_id=user_id)
        if not bot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found",
            )
        if len(message) > 2048:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message exceeds 2048 characters",
            )
        session = self._get_or_create_session(db, user_id=user_id, bot_id=bot_id, session_id=session_id)
        self.repository.insert_chat_message(db, session_id=session["id"], role="user", content=message)
        db.commit()

        history_messages = self.repository.list_messages_for_session(db, session["id"])
        history = [{"role": msg["role"], "content": msg["content"]} for msg in history_messages[:-1]]

        try:
            response_text, llm_usage = await langchain_service.process_message(
                message=message,
                history=history,
                bot_config=bot["config"],
                system_prompt=bot["system_prompt"],
                db=db,
                workspace_id=bot["workspace_id"],
            )
            assistant_message = self.repository.insert_chat_message(
                db,
                session_id=session["id"],
                role="assistant",
                content=response_text,
                metadata={
                    "input_tokens": llm_usage.get("input_tokens"),
                    "output_tokens": llm_usage.get("output_tokens"),
                    "model": llm_usage.get("model"),
                },
            )
            self._apply_usage_charge(
                db,
                workspace_id=bot["workspace_id"],
                assistant_message_id=assistant_message["id"],
                llm_usage=llm_usage,
            )
            db.commit()
            return {
                "session_id": session["id"],
                "assistant_message": assistant_message,
            }
        except Exception as error:
            self.repository.insert_chat_message(
                db,
                session_id=session["id"],
                role="assistant",
                content=f"Error: {str(error)}",
                metadata={"error": True},
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing message: {str(error)}",
            ) from error

    def list_chat_messages(self, db: DatabaseSession, *, user_id: int, session_id: int) -> list[dict]:
        session = self.repository.get_chat_session_for_user(db, session_id=session_id, user_id=user_id)
        if session:
            return self.repository.list_messages_for_session(db, session_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    def list_chat_sessions(self, db: DatabaseSession, *, user_id: int, bot_id: int | None) -> list[dict]:
        sessions = self.repository.list_chat_sessions_for_user(db, user_id=user_id, bot_id=bot_id)
        return [
            {
                "id": session["id"],
                "bot_id": session["bot_id"],
                "created_at": session["created_at"].isoformat() if session.get("created_at") else None,
            }
            for session in sessions
        ]

    def _get_or_create_session(
        self,
        db: DatabaseSession,
        *,
        user_id: int,
        bot_id: int,
        session_id: int | None,
    ) -> dict:
        if session_id:
            session = self.repository.get_chat_session_for_user(
                db,
                session_id=session_id,
                user_id=user_id,
                bot_id=bot_id,
            )
            if session:
                return session
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found",
            )
        session = self.repository.create_chat_session(db, bot_id=bot_id, user_id=user_id)
        db.commit()
        return session

    def _apply_usage_charge(
        self,
        db: DatabaseSession,
        *,
        workspace_id: int,
        assistant_message_id: int,
        llm_usage: dict,
    ) -> None:
        model_name = normalize_model_name(llm_usage.get("model"))
        input_tokens = int(llm_usage.get("input_tokens") or 0)
        output_tokens = int(llm_usage.get("output_tokens") or 0)
        cost = calculate_llm_cost_usd(
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if cost <= 0:
            return
        self.repository.adjust_workspace_balance(
            db,
            workspace_id=workspace_id,
            amount_delta=-cost,
        )
        self.repository.create_billing_transaction(
            db,
            workspace_id=workspace_id,
            transaction_type="usage_charge",
            amount_usd=-cost,
            description="LLM usage charge",
            related_message_id=assistant_message_id,
            metadata_json={
                "model": model_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )
