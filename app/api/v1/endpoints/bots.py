import datetime
from typing import Any, Dict, List, Optional, Literal, Set

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_core.core_schema import ValidationInfo

from app.api.dependencies import get_current_user, get_user_workspace
from app.db import repositories as repo
from app.db.database import DatabaseSession, get_db

router = APIRouter()


class TransitionCondition(BaseModel):
    """Условие перехода между узлами."""
    type: Literal["always", "keyword"] = "always"
    value: Optional[str] = None

    @field_validator("value")
    @classmethod
    def ensure_value_for_keyword(
        cls,
        value: Optional[str],
        info: ValidationInfo,
    ):
        if info.data.get("type") == "keyword" and not value:
            raise ValueError("value is required for 'keyword' transition condition")
        return value


class NodeTransition(BaseModel):
    """Описание перехода между узлами."""
    target_node_id: str
    condition: TransitionCondition = Field(default_factory=TransitionCondition)


class GraphNode(BaseModel):
    """Узел графа LangGraph."""
    id: str
    name: str
    system_prompt: Optional[str] = None
    use_rag: bool = False
    rag_settings: Optional[dict] = None
    allowed_document_ids: List[int] = Field(default_factory=list)
    api_tool_ids: List[int] = Field(default_factory=list)
    transitions: List[NodeTransition] = Field(default_factory=list)


class BotGraphConfig(BaseModel):
    """Граф конфигурации бота."""
    entry_node_id: str
    nodes: List[GraphNode]


class BotCreate(BaseModel):
    name: str
    workspace_id: int
    system_prompt: str
    graph: BotGraphConfig
    temperature: str = "0.7"
    max_tokens: int = 2048


class BotUpdate(BaseModel):
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    graph: Optional[BotGraphConfig] = None
    temperature: Optional[str] = None
    max_tokens: Optional[int] = None


class BotResponse(BaseModel):
    id: int
    name: str
    workspace_id: int
    system_prompt: str
    config: dict
    temperature: str
    max_tokens: int
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True


@router.post("/", response_model=BotResponse, status_code=status.HTTP_201_CREATED)
async def create_bot(
    bot_data: BotCreate,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Создание нового бота"""
    # Проверка доступа к workspace
    workspace = await get_user_workspace(bot_data.workspace_id, current_user, db)
    
    # Валидация системного промпта
    if len(bot_data.system_prompt) > 4096:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System prompt exceeds 4096 characters"
        )
    
    _validate_graph_config(bot_data.graph, bot_data.workspace_id, db)
    bot = repo.create_bot(
        db,
        name=bot_data.name,
        workspace_id=bot_data.workspace_id,
        system_prompt=bot_data.system_prompt,
        config=bot_data.graph.model_dump(),
        temperature=bot_data.temperature,
        max_tokens=bot_data.max_tokens,
    )
    
    db.commit()
    return bot


@router.get("/", response_model=List[BotResponse])
async def get_bots(
    workspace_id: Optional[int] = None,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка ботов"""
    return repo.list_bots_for_owner(
        db,
        owner_id=current_user["id"],
        workspace_id=workspace_id,
    )


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение бота по ID"""
    bot = repo.get_bot_for_owner(db, bot_id=bot_id, owner_id=current_user["id"])
    
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found"
        )
    
    return bot


@router.put("/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: int,
    bot_data: BotUpdate,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Обновление бота"""
    existing_bot = repo.get_bot_for_owner(db, bot_id=bot_id, owner_id=current_user["id"])
    
    if not existing_bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found"
        )
    
    updates: Dict[str, Any] = {}
    if bot_data.name is not None:
        updates["name"] = bot_data.name
    if bot_data.system_prompt is not None:
        if len(bot_data.system_prompt) > 4096:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="System prompt exceeds 4096 characters",
            )
        updates["system_prompt"] = bot_data.system_prompt
    if bot_data.graph is not None:
        _validate_graph_config(bot_data.graph, existing_bot["workspace_id"], db)
        updates["config"] = bot_data.graph.model_dump()
    if bot_data.temperature is not None:
        updates["temperature"] = bot_data.temperature
    if bot_data.max_tokens is not None:
        updates["max_tokens"] = bot_data.max_tokens
    
    updated_bot = repo.update_bot_for_owner(
        db,
        bot_id=bot_id,
        owner_id=current_user["id"],
        updates=updates,
    )
    if not updated_bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )
    
    db.commit()
    return updated_bot


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    bot_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Удаление бота"""
    deleted = repo.delete_bot_for_owner(
        db,
        bot_id=bot_id,
        owner_id=current_user["id"],
    )
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found"
        )
    
    db.commit()
    
    return None


def _validate_graph_config(graph: BotGraphConfig, workspace_id: int, db: DatabaseSession) -> None:
    """Проверка конфигурации графа бота."""
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

    available_doc_ids = {
        document["id"] for document in repo.list_documents_for_workspace(db, workspace_id)
    }
    available_tool_ids = {
        tool["id"] for tool in repo.list_api_tools_for_workspace(db, workspace_id)
    }

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

        for transition in node.transitions:
            if transition.target_node_id not in unique_node_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Node '{node.id}' has transition to unknown node "
                        f"'{transition.target_node_id}'"
                    ),
                )

