from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.db import models as m
from app.db.repository_utils import document_to_dict


class DocumentRepository:
    def create_document(
        self,
        db: Session,
        *,
        workspace_id: int,
        filename: str,
        file_path: str,
        file_size: int,
        file_type: str,
    ) -> dict:
        doc = m.Document(
            workspace_id=workspace_id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
            status="processing",
        )
        db.add(doc)
        db.flush()
        return document_to_dict(doc)

    def list_documents_for_workspace(self, db: Session, workspace_id: int) -> list[dict]:
        rows = db.scalars(
            select(m.Document).where(m.Document.workspace_id == workspace_id).order_by(m.Document.created_at.desc())
        ).all()
        return [document_to_dict(row) for row in rows]

    def get_document_for_user(self, db: Session, *, document_id: int, user_id: int) -> Optional[dict]:
        workspace_user = aliased(m.WorkspaceUser)
        doc = db.scalars(
            select(m.Document)
            .join(m.Workspace, m.Workspace.id == m.Document.workspace_id)
            .outerjoin(workspace_user, and_(workspace_user.workspace_id == m.Workspace.id, workspace_user.user_id == user_id))
            .where(m.Document.id == document_id)
            .where(or_(m.Workspace.owner_id == user_id, workspace_user.user_id == user_id))
        ).first()
        return document_to_dict(doc) if doc else None

    def get_document_for_owner(self, db: Session, *, document_id: int, owner_id: int) -> Optional[dict]:
        doc = db.scalars(
            select(m.Document)
            .join(m.Workspace, m.Workspace.id == m.Document.workspace_id)
            .where(m.Document.id == document_id, m.Workspace.owner_id == owner_id)
        ).first()
        return document_to_dict(doc) if doc else None

    def list_chunk_embedding_ids(self, db: Session, document_id: int) -> list[str]:
        rows = db.scalars(
            select(m.DocumentChunk.embedding_id).where(
                m.DocumentChunk.document_id == document_id,
                m.DocumentChunk.embedding_id.isnot(None),
            )
        ).all()
        return [row for row in rows if row]

    def delete_document_by_id(self, db: Session, document_id: int) -> bool:
        result = db.execute(delete(m.Document).where(m.Document.id == document_id))
        return result.rowcount > 0

    def get_document_by_id(self, db: Session, document_id: int) -> Optional[dict]:
        doc = db.get(m.Document, document_id)
        return document_to_dict(doc) if doc else None

    def update_document_status(
        self,
        db: Session,
        *,
        document_id: int,
        status: str,
        processed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> Optional[dict]:
        doc = db.get(m.Document, document_id)
        if not doc:
            return None
        doc.status = status
        doc.processed_at = processed_at
        doc.error_message = error_message
        db.flush()
        return document_to_dict(doc)

    def insert_document_chunk(
        self,
        db: Session,
        *,
        document_id: int,
        chunk_text: str,
        chunk_index: int,
        embedding_id: Optional[str] = None,
    ) -> dict:
        chunk = m.DocumentChunk(
            document_id=document_id,
            chunk_text=chunk_text,
            chunk_index=chunk_index,
            embedding_id=embedding_id,
        )
        db.add(chunk)
        db.flush()
        return {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "chunk_text": chunk.chunk_text,
            "chunk_index": chunk.chunk_index,
            "created_at": chunk.created_at,
        }

    def update_chunk_embedding_id(self, db: Session, *, chunk_id: int, embedding_id: str) -> None:
        db.execute(update(m.DocumentChunk).where(m.DocumentChunk.id == chunk_id).values(embedding_id=embedding_id))
