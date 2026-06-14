import datetime
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
from pydantic import BaseModel

from app.api.dependencies import get_current_user, get_user_workspace, check_workspace_access
from app.core.config import settings
from app.db.database import DatabaseSession, get_db
from app.db.document_repository import DocumentRepository
from app.services.document_service import DocumentService
from app.services.plan_guard import enforce_document_limit

router = APIRouter()
document_service = DocumentService(DocumentRepository())

# Создаем директорию для загрузок
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_size: int
    file_type: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime.datetime
    processed_at: Optional[datetime.datetime] = None
    
    class Config:
        from_attributes = True


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Загрузка документа"""
    # Проверка доступа к workspace
    workspace = await get_user_workspace(workspace_id, current_user, db)
    enforce_document_limit(db, workspace["id"])
    return await document_service.upload_document(
        db,
        workspace_id=workspace_id,
        file=file,
        background_tasks=background_tasks,
    )


@router.get("/", response_model=List[DocumentResponse])
async def get_documents(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка документов (доступно владельцам и участникам)"""
    await check_workspace_access(workspace_id, current_user, db)
    
    return document_service.list_documents_for_workspace(db, workspace_id)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение документа по ID (доступно владельцам и участникам)"""
    return document_service.get_document_for_user(db, document_id=document_id, user_id=current_user["id"])


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Удаление документа"""
    document_service.delete_document_for_owner(db, document_id=document_id, owner_id=current_user["id"])
    return None

