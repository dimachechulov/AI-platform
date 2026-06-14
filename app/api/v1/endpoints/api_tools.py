import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.dependencies import get_current_user, get_user_workspace, check_workspace_access
from app.db.database import DatabaseSession, get_db
from app.db.api_tool_repository import ApiToolRepository
from app.services.api_tools_service import ApiToolsService

router = APIRouter()
api_tools_service = ApiToolsService(ApiToolRepository())

import logging

logger = logging.getLogger(__name__)


class APIToolCreate(BaseModel):
    workspace_id: int
    name: str
    description: str = None
    url: str
    method: str  # GET, POST, PUT, DELETE
    headers: dict = None
    params: dict = None
    body_schema: dict = None


class APIToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    headers: Optional[dict] = None
    params: Optional[dict] = None
    body_schema: Optional[dict] = None


class APIToolResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str = None
    url: str
    method: str
    headers: dict = None
    params: dict = None
    body_schema: Optional[dict] = None
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True


@router.post("/", response_model=APIToolResponse, status_code=status.HTTP_201_CREATED)
async def create_api_tool(
    tool_data: APIToolCreate,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Создание нового API инструмента"""
    await get_user_workspace(tool_data.workspace_id, current_user, db)
    return api_tools_service.create_api_tool(
        db,
        workspace_id=tool_data.workspace_id,
        name=tool_data.name,
        description=tool_data.description,
        url=tool_data.url,
        method=tool_data.method,
        headers=tool_data.headers,
        params=tool_data.params,
        body_schema=tool_data.body_schema,
    )


@router.get("/", response_model=List[APIToolResponse])
async def get_api_tools(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка API инструментов (доступно владельцам и участникам)"""
    await check_workspace_access(workspace_id, current_user, db)
    
    return api_tools_service.list_api_tools_for_workspace(db, workspace_id)


@router.get("/{tool_id}", response_model=APIToolResponse)
async def get_api_tool(
    tool_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение API инструмента по ID (доступно владельцам и участникам)"""
    tool = api_tools_service.get_api_tool_for_user(db, tool_id=tool_id, user_id=current_user["id"])
    logger.debug("Loaded API tool %s", tool.get("id"))
    return tool


@router.put("/{tool_id}", response_model=APIToolResponse)
async def update_api_tool(
    tool_id: int,
    tool_data: APIToolUpdate,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Обновление API инструмента"""
    return api_tools_service.update_api_tool_for_owner(
        db,
        tool_id=tool_id,
        owner_id=current_user["id"],
        name=tool_data.name,
        description=tool_data.description,
        url=tool_data.url,
        method=tool_data.method,
        headers=tool_data.headers,
        params=tool_data.params,
        body_schema=tool_data.body_schema,
    )


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_tool(
    tool_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Удаление API инструмента"""
    api_tools_service.delete_api_tool_for_owner(
        db,
        tool_id=tool_id,
        owner_id=current_user["id"],
    )
    return None

