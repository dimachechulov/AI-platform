from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session, aliased

from app.db import models as m
from app.db.repository_utils import bot_to_dict, load_bot_configs


class BotRepository:
    def create_bot(
        self,
        db: Session,
        *,
        name: str,
        workspace_id: int,
        system_prompt: str,
        config: dict,
        temperature: str,
        max_tokens: int,
    ) -> dict:
        bot = m.Bot(
            name=name,
            workspace_id=workspace_id,
            system_prompt=system_prompt,
            temperature=float(temperature),
            max_tokens=max_tokens,
        )
        db.add(bot)
        db.flush()
        if config:
            for key, value in config.items():
                value_type = type(value).__name__
                if value_type in ("int", "float"):
                    value_type, stored_value = "number", str(value)
                elif value_type == "bool":
                    value_type, stored_value = "boolean", str(value)
                elif value_type in ("list", "tuple"):
                    value_type, stored_value = "array", json.dumps(value)
                elif value_type == "dict":
                    value_type, stored_value = "object", json.dumps(value)
                else:
                    value_type, stored_value = "string", str(value)
                db.add(m.BotConfig(bot_id=bot.id, config_key=key, config_value=stored_value, value_type=value_type))
        db.flush()
        cfg_rows = db.scalars(select(m.BotConfig).where(m.BotConfig.bot_id == bot.id)).all()
        return bot_to_dict(bot, list(cfg_rows))

    def list_bots_for_user(self, db: Session, *, user_id: int, workspace_id: Optional[int] = None) -> list[dict]:
        workspace_user = aliased(m.WorkspaceUser)
        stmt = (
            select(m.Bot)
            .join(m.Workspace, m.Workspace.id == m.Bot.workspace_id)
            .outerjoin(workspace_user, and_(workspace_user.workspace_id == m.Workspace.id, workspace_user.user_id == user_id))
            .where(or_(m.Workspace.owner_id == user_id, workspace_user.user_id == user_id))
        )
        if workspace_id is not None:
            stmt = stmt.where(m.Bot.workspace_id == workspace_id)
        stmt = stmt.order_by(m.Bot.created_at.desc())
        bots = db.scalars(stmt).all()
        out = []
        seen: set[int] = set()
        for bot in bots:
            if bot.id in seen:
                continue
            seen.add(bot.id)
            out.append(bot_to_dict(bot, load_bot_configs(db, bot.id)))
        return out

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

    def get_bot_for_owner(self, db: Session, *, bot_id: int, owner_id: int) -> Optional[dict]:
        bot = db.scalars(
            select(m.Bot).join(m.Workspace, m.Workspace.id == m.Bot.workspace_id).where(m.Bot.id == bot_id, m.Workspace.owner_id == owner_id)
        ).first()
        if not bot:
            return None
        return bot_to_dict(bot, load_bot_configs(db, bot.id))

    def update_bot_for_owner(
        self,
        db: Session,
        *,
        bot_id: int,
        owner_id: int,
        updates: Dict[str, Any],
    ) -> Optional[dict]:
        if not updates:
            return self.get_bot_for_owner(db, bot_id=bot_id, owner_id=owner_id)
        config = updates.pop("config", None)
        bot = db.scalars(
            select(m.Bot).join(m.Workspace, m.Workspace.id == m.Bot.workspace_id).where(m.Bot.id == bot_id, m.Workspace.owner_id == owner_id)
        ).first()
        if not bot:
            return None
        if updates:
            if "temperature" in updates:
                updates["temperature"] = float(updates["temperature"])
            for key, value in updates.items():
                setattr(bot, key, value)
        if config is not None:
            db.execute(delete(m.BotConfig).where(m.BotConfig.bot_id == bot_id))
            if config:
                for key, value in config.items():
                    value_type = type(value).__name__
                    if value_type in ("int", "float"):
                        value_type, stored_value = "number", str(value)
                    elif value_type == "bool":
                        value_type, stored_value = "boolean", str(value)
                    elif value_type in ("list", "tuple"):
                        value_type, stored_value = "array", json.dumps(value)
                    elif value_type == "dict":
                        value_type, stored_value = "object", json.dumps(value)
                    else:
                        value_type, stored_value = "string", str(value)
                    db.add(m.BotConfig(bot_id=bot_id, config_key=key, config_value=stored_value, value_type=value_type))
            db.flush()
        cfg_rows = load_bot_configs(db, bot_id)
        return bot_to_dict(bot, cfg_rows)

    def delete_bot_for_owner(self, db: Session, *, bot_id: int, owner_id: int) -> bool:
        workspace_ids = select(m.Workspace.id).where(m.Workspace.owner_id == owner_id).scalar_subquery()
        result = db.execute(delete(m.Bot).where(m.Bot.id == bot_id, m.Bot.workspace_id.in_(workspace_ids)))
        return result.rowcount > 0

    def list_documents_for_workspace(self, db: Session, workspace_id: int) -> list[dict]:
        from app.db.document_repository import DocumentRepository

        return DocumentRepository().list_documents_for_workspace(db, workspace_id)

    def list_api_tools_for_workspace(self, db: Session, workspace_id: int) -> list[dict]:
        from app.db.api_tool_repository import ApiToolRepository

        return ApiToolRepository().list_api_tools_for_workspace(db, workspace_id)
