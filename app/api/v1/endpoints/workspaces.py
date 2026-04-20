from datetime import datetime
from typing import List

from typing import Dict

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.db.database import DatabaseSession, get_db
from app.db.workspace_repository import WorkspaceRepository
from app.services.workspace_service import WorkspaceService

router = APIRouter()
workspace_service = WorkspaceService(WorkspaceRepository())


class WorkspaceCreate(BaseModel):
    name: str


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    created_at: datetime
    user_role: str = "owner"  # owner, member, etc.
    
    class Config:
        from_attributes = True


class WorkspaceUserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: str
    added_at: datetime
    
    class Config:
        from_attributes = True


class AddUserToWorkspaceRequest(BaseModel):
    user_email: str
    role: str = "member"


@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    workspace_data: WorkspaceCreate,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Создание нового рабочего пространства"""
    return workspace_service.create_workspace(
        db,
        owner_id=current_user["id"],
        name=workspace_data.name,
    )


@router.get("/", response_model=List[WorkspaceResponse])
async def get_workspaces(
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка рабочих пространств пользователя (владелец + участник)"""
    return workspace_service.list_user_workspaces(db, current_user["id"])


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение рабочего пространства по ID"""
    return workspace_service.get_workspace_for_user(
        db,
        workspace_id=workspace_id,
        user_id=current_user["id"],
    )


@router.get("/{workspace_id}/users", response_model=List[WorkspaceUserResponse])
async def list_workspace_users(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка пользователей воркспейса (только для владельца)"""
    return workspace_service.list_workspace_users_for_owner(
        db,
        workspace_id=workspace_id,
        owner_id=current_user["id"],
    )


@router.post("/{workspace_id}/users", response_model=WorkspaceUserResponse, status_code=status.HTTP_201_CREATED)
async def add_user_to_workspace(
    workspace_id: int,
    request: AddUserToWorkspaceRequest,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Добавление пользователя в воркспейс (только для владельца)"""
    return workspace_service.add_user_to_workspace(
        db,
        workspace_id=workspace_id,
        owner_user=current_user,
        user_email=request.user_email,
        role=request.role,
    )


@router.delete("/{workspace_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_workspace(
    workspace_id: int,
    user_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Удаление пользователя из воркспейса (только для владельца)"""
    workspace_service.remove_user_from_workspace(
        db,
        workspace_id=workspace_id,
        owner_id=current_user["id"],
        user_id=user_id,
    )
    return None

