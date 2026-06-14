from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import models as m
from app.db.billing_repository import BillingRepository
from app.db.repository_utils import build_metadata_dict


class ChatRepository:
    def __init__(self) -> None:
        self._billing_repo = BillingRepository()

    def get_bot_for_user(self, db: Session, *, bot_id: int, user_id: int) -> Optional[dict]:
        from app.db.bot_repository import BotRepository

        return BotRepository().get_bot_for_user(db, bot_id=bot_id, user_id=user_id)

    def get_chat_session_for_user(
        self,
        db: Session,
        *,
        session_id: int,
        user_id: int,
        bot_id: Optional[int] = None,
    ) -> Optional[dict]:
        stmt = select(m.ChatSession).where(m.ChatSession.id == session_id, m.ChatSession.user_id == user_id)
        if bot_id is not None:
            stmt = stmt.where(m.ChatSession.bot_id == bot_id)
        session = db.scalars(stmt).first()
        if not session:
            return None
        return {
            "id": session.id,
            "bot_id": session.bot_id,
            "user_id": session.user_id,
            "created_at": session.created_at,
            "last_activity_at": session.last_activity_at,
            "message_count": session.message_count,
        }

    def create_chat_session(self, db: Session, *, bot_id: int, user_id: int) -> dict:
        session = m.ChatSession(bot_id=bot_id, user_id=user_id)
        db.add(session)
        db.flush()
        return {
            "id": session.id,
            "bot_id": session.bot_id,
            "user_id": session.user_id,
            "created_at": session.created_at,
            "last_activity_at": session.last_activity_at,
            "message_count": session.message_count,
        }

    def insert_chat_message(
        self,
        db: Session,
        *,
        session_id: int,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        filtered_metadata = None
        if metadata:
            filtered_metadata = {k: v for k, v in metadata.items() if v is not None}
            if not filtered_metadata:
                filtered_metadata = None
        row = db.execute(
            text("SELECT * FROM create_chat_message(:sid, :role, :content, :meta)"),
            {
                "sid": session_id,
                "role": role,
                "content": content,
                "meta": json.dumps(filtered_metadata) if filtered_metadata else None,
            },
        ).mappings().one()
        msg = {k: row[k] for k in row.keys()}
        if metadata:
            msg["message_metadata"] = metadata
        return msg

    def list_messages_for_session(self, db: Session, session_id: int) -> list[dict]:
        messages = db.scalars(
            select(m.ChatMessage).where(m.ChatMessage.session_id == session_id).order_by(m.ChatMessage.created_at.asc())
        ).all()
        out = []
        for message in messages:
            meta_rows = db.scalars(select(m.ChatMessageMetadata).where(m.ChatMessageMetadata.message_id == message.id)).all()
            out.append(
                {
                    "id": message.id,
                    "session_id": message.session_id,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at,
                    "message_metadata": build_metadata_dict(list(meta_rows)),
                }
            )
        return out

    def list_chat_sessions_for_user(
        self,
        db: Session,
        *,
        user_id: int,
        bot_id: Optional[int] = None,
    ) -> list[dict]:
        stmt = select(m.ChatSession).where(m.ChatSession.user_id == user_id)
        if bot_id is not None:
            stmt = stmt.where(m.ChatSession.bot_id == bot_id)
        stmt = stmt.order_by(m.ChatSession.last_activity_at.desc(), m.ChatSession.created_at.desc())
        rows = db.scalars(stmt).all()
        return [
            {
                "id": row.id,
                "bot_id": row.bot_id,
                "user_id": row.user_id,
                "created_at": row.created_at,
                "last_activity_at": row.last_activity_at,
                "message_count": row.message_count,
            }
            for row in rows
        ]

    def adjust_workspace_balance(
        self,
        db: Session,
        *,
        workspace_id: int,
        amount_delta: Decimal,
    ) -> Optional[dict]:
        return self._billing_repo.adjust_workspace_balance(db, workspace_id=workspace_id, amount_delta=amount_delta)

    def create_billing_transaction(
        self,
        db: Session,
        *,
        workspace_id: int,
        transaction_type: str,
        amount_usd: Decimal,
        description: Optional[str] = None,
        related_message_id: Optional[int] = None,
        stripe_event_id: Optional[str] = None,
        metadata_json: Optional[dict] = None,
    ) -> dict:
        return self._billing_repo.create_billing_transaction(
            db,
            workspace_id=workspace_id,
            transaction_type=transaction_type,
            amount_usd=amount_usd,
            description=description,
            related_message_id=related_message_id,
            stripe_event_id=stripe_event_id,
            metadata_json=metadata_json,
        )
