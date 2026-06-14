from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException, status

from app.db.database import DatabaseSession
from app.db.bot_repository import BotRepository


class BotService:
    def __init__(self, repository: BotRepository):
        self.repository = repository

    def create_bot(
        self,
        db: DatabaseSession,
        *,
        name: str,
        workspace_id: int,
        system_prompt: str,
        graph: dict,
        temperature: str,
        max_tokens: int,
    ) -> dict:
        self._validate_system_prompt(system_prompt)
        bot = self.repository.create_bot(
            db,
            name=name,
            workspace_id=workspace_id,
            system_prompt=system_prompt,
            config=graph,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        db.commit()
        return bot

    def list_bots_for_user(self, db: DatabaseSession, *, user_id: int, workspace_id: int | None) -> list[dict]:
        return self.repository.list_bots_for_user(db, user_id=user_id, workspace_id=workspace_id)

    def get_bot_for_user(self, db: DatabaseSession, *, bot_id: int, user_id: int) -> dict:
        bot = self.repository.get_bot_for_user(db, bot_id=bot_id, user_id=user_id)
        if bot:
            return bot
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    def update_bot_for_owner(
        self,
        db: DatabaseSession,
        *,
        bot_id: int,
        owner_id: int,
        updates: Dict[str, Any],
    ) -> dict:
        if "system_prompt" in updates:
            self._validate_system_prompt(str(updates["system_prompt"]))
        updated_bot = self.repository.update_bot_for_owner(
            db,
            bot_id=bot_id,
            owner_id=owner_id,
            updates=updates,
        )
        if not updated_bot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found",
            )
        db.commit()
        return updated_bot

    def delete_bot_for_owner(self, db: DatabaseSession, *, bot_id: int, owner_id: int) -> None:
        deleted = self.repository.delete_bot_for_owner(db, bot_id=bot_id, owner_id=owner_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found",
            )
        db.commit()

    def validate_graph_config(self, db: DatabaseSession, *, graph: Any, workspace_id: int) -> None:
        if not graph.nodes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Graph must contain at least one node",
            )

        node_ids = [node.id for node in graph.nodes]
        unique_node_ids = set(node_ids)
        if len(unique_node_ids) != len(node_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Graph node ids must be unique",
            )
        if graph.entry_node_id not in unique_node_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Entry node id must reference an existing node",
            )

        available_doc_ids = {document["id"] for document in self.repository.list_documents_for_workspace(db, workspace_id)}
        available_tool_ids = {tool["id"] for tool in self.repository.list_api_tools_for_workspace(db, workspace_id)}

        for node in graph.nodes:
            invalid_docs = set(node.allowed_document_ids) - available_doc_ids
            if invalid_docs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Node '{node.id}' references unknown document ids: {sorted(invalid_docs)}",
                )
            invalid_tools = set(node.api_tool_ids) - available_tool_ids
            if invalid_tools:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Node '{node.id}' references unknown API tool ids: {sorted(invalid_tools)}",
                )
            if len(node.transitions) > 1 and any(t.condition.type == "always" for t in node.transitions):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Node '{node.id}': a transition with condition 'always' "
                        f"cannot coexist with other outgoing transitions"
                    ),
                )
            for transition in node.transitions:
                if transition.target_node_id not in unique_node_ids:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Node '{node.id}' has transition to unknown node "
                            f"'{transition.target_node_id}'"
                        ),
                    )

    @staticmethod
    def _validate_system_prompt(system_prompt: str) -> None:
        if len(system_prompt) <= 4096:
            return
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System prompt exceeds 4096 characters",
        )
