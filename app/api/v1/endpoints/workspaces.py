from datetime import datetime
from typing import List

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.db import repositories as repo
from app.db.database import DatabaseSession, get_db

router = APIRouter()


class WorkspaceCreate(BaseModel):
    name: str


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    workspace_data: WorkspaceCreate,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Создание нового рабочего пространства"""
    workspace = repo.create_workspace(
        db,
        owner_id=current_user["id"],
        name=workspace_data.name,
    )
    db.commit()
    return workspace


@router.get("/", response_model=List[WorkspaceResponse])
async def get_workspaces(
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка рабочих пространств пользователя"""
    return repo.list_workspaces_for_owner(db, current_user["id"])


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение рабочего пространства по ID"""
    workspace = repo.get_workspace_for_owner(
        db,
        workspace_id=workspace_id,
        owner_id=current_user["id"],
    )
    
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )
    
    return workspace

