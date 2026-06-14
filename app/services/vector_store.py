"""RAG embeddings and retrieval via LangChain `PGVector` (langchain_community)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_community.vectorstores import PGVector
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import settings

# Gemini text-embedding-004 dimension
_EMBEDDING_LENGTH = 3072


@dataclass
class VectorSearchResult:
    page_content: str
    metadata: Dict[str, Any]


def _embeddings() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=settings.GEMINI_API_KEY,
        #request_parallelism=1,  # Отключает batch-режим
    task_type="RETRIEVAL_DOCUMENT",
    transport="rest",
    )


def _pgvector(workspace_id: int) -> PGVector:
    """One LangChain collection per workspace (multi-tenant isolation)."""
    return PGVector(
        connection_string=settings.DATABASE_URL,
        embedding_function=_embeddings(),
        collection_name=f"workspace_{workspace_id}",
        embedding_length=_EMBEDDING_LENGTH,
        use_jsonb=True,
    )


class VectorStoreService:
    """Thin facade over LangChain PGVector for chunk add / delete / similarity search."""

    def add_chunks(self, workspace_id: int, chunk_payloads: List[Dict[str, Any]]) -> List[tuple[int, str]]:
        """Embed texts, store in PGVector, return list of (chunk_id, langchain_row_id)."""
        if not chunk_payloads:
            return []

        store = _pgvector(workspace_id)
        texts = [p["text"] for p in chunk_payloads]
        metadatas: List[Dict[str, Any]] = []
        for p in chunk_payloads:
            meta = dict(p["metadata"])
            # JSON-friendly metadata for PGVector filters
            for k, v in list(meta.items()):
                if isinstance(v, bool):
                    meta[k] = v
                elif isinstance(v, (int, float)):
                    meta[k] = v
                elif v is not None:
                    meta[k] = str(v)
            metadatas.append(meta)

        ids = []
        for text, meta in zip(texts, metadatas):
            ids.extend(
                store.add_texts(
                    texts=[text],
                    metadatas=[meta],
                )
            )
        out: List[tuple[int, str]] = []
        for payload, lid in zip(chunk_payloads, ids, strict=True):
            out.append((payload["id"], lid))
        return out

    def delete_embeddings(self, workspace_id: int, langchain_ids: List[str]) -> None:
        if not langchain_ids:
            return
        store = _pgvector(workspace_id)
        store.delete(ids=langchain_ids)

    def search_similar_chunks(
        self,
        workspace_id: int,
        query_text: str,
        k: int = 5,
    ) -> List[VectorSearchResult]:
        try:
            store = _pgvector(workspace_id)
            docs = store.similarity_search(query_text, k=k)
        except Exception:
            return []

        results: List[VectorSearchResult] = []
        for doc in docs:
            results.append(
                VectorSearchResult(
                    page_content=doc.page_content,
                    metadata=dict(doc.metadata) if doc.metadata else {},
                )
            )
        return results


vector_store = VectorStoreService()
