from __future__ import annotations

import os
from typing import Optional

import aiofiles
from fastapi import BackgroundTasks, HTTPException, UploadFile, status

from app.core.config import settings
from app.db.database import DatabaseSession
from app.db.document_repository import DocumentRepository
from app.services.document_processor_service import process_document_async
from app.services.vector_store import vector_store

ALLOWED_FILE_TYPES = {"pdf", "docx", "txt"}


class DocumentService:
    def __init__(self, repository: DocumentRepository):
        self.repository = repository

    async def upload_document(
        self,
        db: DatabaseSession,
        *,
        workspace_id: int,
        file: UploadFile,
        background_tasks: BackgroundTasks,
    ) -> dict:
        file_type = self._validate_and_extract_file_type(file.filename)
        file_content = await file.read()
        file_size = len(file_content)
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE / 1024 / 1024} MB",
            )
        file_path = os.path.join(settings.UPLOAD_DIR, f"{workspace_id}_{file.filename}")
        async with aiofiles.open(file_path, "wb") as output:
            await output.write(file_content)
        document = self.repository.create_document(
            db,
            workspace_id=workspace_id,
            filename=file.filename,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
        )
        db.commit()
        background_tasks.add_task(process_document_async, document["id"])
        return document

    def list_documents_for_workspace(self, db: DatabaseSession, workspace_id: int) -> list[dict]:
        return self.repository.list_documents_for_workspace(db, workspace_id)

    def get_document_for_user(self, db: DatabaseSession, *, document_id: int, user_id: int) -> dict:
        document = self.repository.get_document_for_user(db, document_id=document_id, user_id=user_id)
        if document:
            return document
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    def delete_document_for_owner(self, db: DatabaseSession, *, document_id: int, owner_id: int) -> None:
        document = self.repository.get_document_for_owner(db, document_id=document_id, owner_id=owner_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        file_path = document["file_path"]
        if os.path.exists(file_path):
            os.remove(file_path)
        embedding_ids = self.repository.list_chunk_embedding_ids(db, document_id)
        vector_store.delete_embeddings(document["workspace_id"], embedding_ids)
        self.repository.delete_document_by_id(db, document_id)
        db.commit()

    @staticmethod
    def _validate_and_extract_file_type(filename: Optional[str]) -> str:
        if not filename or "." not in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Only PDF, DOCX, TXT are allowed",
            )
        file_type = filename.split(".")[-1].lower()
        if file_type in ALLOWED_FILE_TYPES:
            return file_type
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only PDF, DOCX, TXT are allowed",
        )
