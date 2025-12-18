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
    """Получение списка рабочих пространств пользователя (владелец + участник)"""
    return repo.list_all_workspaces_for_user(db, current_user["id"])


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение рабочего пространства по ID"""
    workspace = repo.check_user_workspace_access(
        db,
        workspace_id=workspace_id,
        user_id=current_user["id"],
    )
    
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied"
        )
    
    return workspace


@router.get("/{workspace_id}/users", response_model=List[WorkspaceUserResponse])
async def list_workspace_users(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка пользователей воркспейса (только для владельца)"""
    # Проверяем, что текущий пользователь - владелец воркспейса
    workspace = repo.get_workspace_for_owner(
        db,
        workspace_id=workspace_id,
        owner_id=current_user["id"],
    )
    
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owner can list users"
        )
    
    return repo.list_workspace_users(db, workspace_id)


@router.post("/{workspace_id}/users", response_model=WorkspaceUserResponse, status_code=status.HTTP_201_CREATED)
async def add_user_to_workspace(
    workspace_id: int,
    request: AddUserToWorkspaceRequest,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Добавление пользователя в воркспейс (только для владельца)"""
    # Проверяем, что текущий пользователь - владелец воркспейса
    workspace = repo.get_workspace_for_owner(
        db,
        workspace_id=workspace_id,
        owner_id=current_user["id"],
    )
    
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owner can add users"
        )
    
    # Находим пользователя по email
    user_to_add = repo.get_user_by_email(db, request.user_email)
    if not user_to_add:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email '{request.user_email}' not found"
        )
    
    # Проверяем, что это не сам владелец
    if user_to_add["id"] == current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add yourself as a member"
        )
    
    # Добавляем пользователя в воркспейс
    repo.add_user_to_workspace(
        db,
        workspace_id=workspace_id,
        user_id=user_to_add["id"],
        role=request.role,
    )
    db.commit()
    
    # Возвращаем информацию о добавленном пользователе
    return {
        "id": user_to_add["id"],
        "email": user_to_add["email"],
        "full_name": user_to_add.get("full_name"),
        "role": request.role,
        "added_at": datetime.now(),
    }


@router.delete("/{workspace_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_workspace(
    workspace_id: int,
    user_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Удаление пользователя из воркспейса (только для владельца)"""
    # Проверяем, что текущий пользователь - владелец воркспейса
    workspace = repo.get_workspace_for_owner(
        db,
        workspace_id=workspace_id,
        owner_id=current_user["id"],
    )
    
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owner can remove users"
        )
    
    # Удаляем пользователя из воркспейса
    success = repo.remove_user_from_workspace(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in workspace"
        )
    
    db.commit()
    return None

