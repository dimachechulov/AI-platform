import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import get_current_user, get_user_workspace
from app.db import repositories as repo
from app.db.database import DatabaseSession, get_db

router = APIRouter()

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
    workspace = await get_user_workspace(tool_data.workspace_id, current_user, db)
    
    # Валидация метода
    if tool_data.method.upper() not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid HTTP method"
        )
    
    tool = repo.create_api_tool(
        db,
        workspace_id=tool_data.workspace_id,
        name=tool_data.name,
        description=tool_data.description,
        url=tool_data.url,
        method=tool_data.method.upper(),
        headers=tool_data.headers,
        params=tool_data.params,
        body_schema=tool_data.body_schema,
    )
    
    db.commit()
    return tool


@router.get("/", response_model=List[APIToolResponse])
async def get_api_tools(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка API инструментов"""
    workspace = await get_user_workspace(workspace_id, current_user, db)
    
    return repo.list_api_tools_for_workspace(db, workspace_id)


@router.get("/{tool_id}", response_model=APIToolResponse)
async def get_api_tool(
    tool_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение API инструмента по ID"""
    tool = repo.get_api_tool_for_owner(db, tool_id=tool_id, owner_id=current_user["id"])
    
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API tool not found"
        )
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
    existing_tool = repo.get_api_tool_for_owner(db, tool_id=tool_id, owner_id=current_user["id"])
    
    if not existing_tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API tool not found"
        )
    
    updates: Dict[str, object] = {}
    if tool_data.name is not None:
        updates["name"] = tool_data.name
    if tool_data.description is not None:
        updates["description"] = tool_data.description
    if tool_data.url is not None:
        updates["url"] = tool_data.url
    if tool_data.method is not None:
        if tool_data.method.upper() not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid HTTP method"
            )
        updates["method"] = tool_data.method.upper()
    if tool_data.headers is not None:
        updates["headers"] = tool_data.headers
    if tool_data.params is not None:
        updates["params"] = tool_data.params
    if tool_data.body_schema is not None:
        updates["body_schema"] = tool_data.body_schema
    
    updated_tool = repo.update_api_tool_for_owner(
        db,
        tool_id=tool_id,
        owner_id=current_user["id"],
        updates=updates,
    )
    if not updated_tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API tool not found"
        )
    
    db.commit()
    return updated_tool


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_tool(
    tool_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Удаление API инструмента"""
    deleted = repo.delete_api_tool_for_owner(
        db,
        tool_id=tool_id,
        owner_id=current_user["id"],
    )
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API tool not found"
        )
    
    db.commit()
    
    return None

