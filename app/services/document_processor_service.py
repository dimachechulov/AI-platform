"""
Сервис для фоновой обработки документов с использованием чистого SQL.
"""
import asyncio
from datetime import datetime
from typing import List, Dict

from app.db import repositories as repo
from app.db.database import db_session
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import vector_store

document_processor = DocumentProcessor()


async def process_document_async(document_id: int):
    """Асинхронная обработка документа."""
    db = db_session()
    try:
        document = repo.get_document_by_id(db, document_id)
        if not document:
            return

        text = await document_processor.process_document(
            document["file_path"],
            document["file_type"],
        )

        chunks = document_processor.split_text_into_chunks(text)
        if not chunks:
            repo.update_document_status(
                db,
                document_id=document_id,
                status="processed",
                processed_at=datetime.utcnow(),
            )
            db.commit()
            return

        chunk_payloads: List[Dict] = []
        for idx, chunk_text in enumerate(chunks):
            chunk = repo.insert_document_chunk(
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

        vector_store.add_chunks(
            workspace_id=document["workspace_id"],
            chunk_payloads=chunk_payloads,
        )

        repo.update_document_status(
            db,
            document_id=document_id,
            status="processed",
            processed_at=datetime.utcnow(),
        )
        db.commit()

    except Exception as exc:
        repo.update_document_status(
            db,
            document_id=document_id,
            status="error",
            error_message=str(exc),
        )
        db.commit()
    finally:
        db.close()


def process_document_background(document_id: int):
    """Запуск обработки документа в фоне."""
    asyncio.create_task(process_document_async(document_id))

