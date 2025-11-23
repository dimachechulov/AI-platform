import datetime
import os
from typing import Dict, List, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.dependencies import get_current_user, get_user_workspace
from app.core.config import settings
from app.db import repositories as repo
from app.db.database import DatabaseSession, get_db
from app.services.document_processor_service import process_document_background
from app.services.vector_store import vector_store

router = APIRouter()

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
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Загрузка документа"""
    # Проверка доступа к workspace
    workspace = await get_user_workspace(workspace_id, current_user, db)
    
    # Проверка типа файла
    file_type = file.filename.split('.')[-1].lower()
    if file_type not in ['pdf', 'docx', 'txt']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only PDF, DOCX, TXT are allowed"
        )
    
    # Проверка размера файла
    file_content = await file.read()
    file_size = len(file_content)
    if file_size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE / 1024 / 1024} MB"
        )
    
    # Сохранение файла
    file_path = os.path.join(settings.UPLOAD_DIR, f"{workspace_id}_{file.filename}")
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(file_content)
    
    # Создание записи в БД
    document = repo.create_document(
        db,
        workspace_id=workspace_id,
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        file_type=file_type,
    )
    db.commit()
    
    # Асинхронная обработка документа в фоне
    process_document_background(document["id"])
    
    return document


@router.get("/", response_model=List[DocumentResponse])
async def get_documents(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение списка документов"""
    workspace = await get_user_workspace(workspace_id, current_user, db)
    
    return repo.list_documents_for_workspace(db, workspace_id)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение документа по ID"""
    document = repo.get_document_for_owner(
        db,
        document_id=document_id,
        owner_id=current_user["id"],
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Удаление документа"""
    document = repo.get_document_for_owner(
        db,
        document_id=document_id,
        owner_id=current_user["id"],
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Удаление файла
    file_path = document["file_path"]
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # Удаляем embeddings из vector store
    chunk_ids = repo.list_document_chunk_ids(db, document_id)
    vector_store.delete_chunks(document["workspace_id"], chunk_ids)
    
    db.execute("DELETE FROM documents WHERE id = %s", (document_id,))
    db.commit()
    
    return None

