"""
Фоновая обработка документов: чанки в БД и эмбеддинги через LangChain PGVector.
"""
import logging
from datetime import datetime
from typing import Dict, List

from app.db.database import db_session
from app.db.document_repository import DocumentRepository
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import vector_store

document_processor = DocumentProcessor()
document_repo = DocumentRepository()
logger = logging.getLogger(__name__)


async def process_document_async(document_id: int):
    """Асинхронная обработка документа."""
    db = db_session()
    try:
        document = document_repo.get_document_by_id(db, document_id)
        if not document:
            return

        text = await document_processor.process_document(
            document["file_path"],
            document["file_type"],
        )

        chunks = document_processor.split_text_into_chunks(text)
        if not chunks:
            document_repo.update_document_status(
                db,
                document_id=document_id,
                status="processed",
                processed_at=datetime.utcnow(),
            )
            db.commit()
            return

        chunk_payloads: List[Dict] = []
        for idx, chunk_text in enumerate(chunks):
            chunk = document_repo.insert_document_chunk(
                db,
                document_id=document_id,
                chunk_text=chunk_text,
                chunk_index=idx,
            )
            chunk_payloads.append(
                {
                    "id": chunk["id"],
                    "text": chunk_text,
                    "metadata": {
                        "chunk_id": chunk["id"],
                        "document_id": document_id,
                        "workspace_id": document["workspace_id"],
                        "filename": document["filename"],
                        "chunk_index": idx,
                    },
                }
            )

        db.commit()

        pairs = vector_store.add_chunks(document["workspace_id"], chunk_payloads)
        for chunk_id, embedding_id in pairs:
            document_repo.update_chunk_embedding_id(db, chunk_id=chunk_id, embedding_id=embedding_id)

        document_repo.update_document_status(
            db,
            document_id=document_id,
            status="processed",
            processed_at=datetime.utcnow(),
        )
        db.commit()

    except Exception as exc:
        db.rollback()
        logger.exception(
            "Обработка документа завершилась с ошибкой (document_id=%s): %s",
            document_id,
            exc,
        )
        document_repo.update_document_status(
            db,
            document_id=document_id,
            status="failed",
            processed_at=datetime.utcnow(),
            error_message=str(exc),
        )
        db.commit()
    finally:
        db.close()
