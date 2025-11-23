from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from psycopg2.extras import Json

from app.core.config import settings
from app.db.database import DatabaseSession, db_session


@dataclass
class VectorSearchResult:
    page_content: str
    metadata: Dict[str, Any]


class VectorStore:
    """Vector store powered by pgvector via direct psycopg2 access."""

    def __init__(self) -> None:
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=settings.GEMINI_API_KEY,
        )

    def _insert_embedding(
        self,
        db: DatabaseSession,
        *,
        chunk_id: int,
        workspace_id: int,
        text: str,
        metadata: Dict[str, Any],
        embedding: List[float],
    ) -> None:
        db.execute(
            """
            INSERT INTO document_chunk_embeddings (chunk_id, workspace_id, content, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id) DO UPDATE
            SET content = EXCLUDED.content,
                metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding
            """,
            (
                chunk_id,
                workspace_id,
                text,
                Json(metadata),
                np.asarray(embedding, dtype=np.float32),
            ),
        )

    def add_chunks(self, workspace_id: int, chunk_payloads: List[Dict[str, Any]]) -> None:
        """Добавление подготовленных chunk'ов в кастомный vector store."""
        if not chunk_payloads:
            return

        texts = [payload["text"] for payload in chunk_payloads]
        embeddings = self.embeddings.embed_documents(texts)

        with db_session() as db:
            for payload, embedding in zip(chunk_payloads, embeddings, strict=True):
                self._insert_embedding(
                    db,
                    chunk_id=payload["id"],
                    workspace_id=workspace_id,
                    text=payload["text"],
                    metadata=payload["metadata"],
                    embedding=embedding,
                )

    def delete_chunks(self, workspace_id: int, chunk_ids: List[int]) -> None:
        """Удаление chunk'ов из vector store по их ID."""
        if not chunk_ids:
            return

        with db_session() as db:
            db.execute(
                """
                DELETE FROM document_chunk_embeddings
                WHERE workspace_id = %s AND chunk_id = ANY(%s)
                """,
                (workspace_id, chunk_ids),
            )

    def search_similar_chunks(
        self,
        workspace_id: int,
        query_text: str,
        k: int = 5,
    ) -> List[VectorSearchResult]:
        """Поиск похожих chunk'ов через pgvector оператор cosine distance."""
        try:
            query_vector = self.embeddings.embed_query(query_text)
        except Exception:
            return []

        with db_session() as db:
            try:
                rows = db.fetch_all(
                    """
                    SELECT content, metadata
                    FROM document_chunk_embeddings
                    WHERE workspace_id = %s
                    ORDER BY embedding <=> %s
                    LIMIT %s
                    """,
                    (workspace_id, np.asarray(query_vector, dtype=np.float32), k),
                )
            except Exception:
                return []

        return [
            VectorSearchResult(
                page_content=row["content"],
                metadata=row.get("metadata") or {},
            )
            for row in rows
        ]


vector_store = VectorStore()

