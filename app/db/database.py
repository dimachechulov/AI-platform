from __future__ import annotations

import json
from threading import Lock
from typing import Any, Iterable, Optional, Sequence

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, register_default_json, register_default_jsonb
from pgvector.psycopg2 import register_vector

from app.core.config import settings

# Ensure JSON/JSONB columns are automatically converted to dict/list objects
register_default_json(loads=lambda value: json.loads(value) if value else None, globally=True)
register_default_jsonb(loads=lambda value: json.loads(value) if value else None, globally=True)

_pool: Optional[pool.SimpleConnectionPool] = None
_pool_lock = Lock()


def _get_pool() -> pool.SimpleConnectionPool:
    """Lazily create a connection pool."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pool.SimpleConnectionPool(
                    minconn=1,
                    maxconn=20,
                    dsn=settings.DATABASE_URL,
                )
    return _pool


class DatabaseSession:
    """Thin wrapper around a psycopg2 connection with helper methods."""

    def __init__(self) -> None:
        self._pool = _get_pool()
        self._conn = self._pool.getconn()
        self._conn.autocommit = False
        register_vector(self._conn)
        self._cursor = self._conn.cursor(cursor_factory=RealDictCursor)

    # Context-manager helpers -------------------------------------------------
    def __enter__(self) -> "DatabaseSession":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

    # Basic cursor helpers ----------------------------------------------------
    def execute(self, query: str, params: Optional[Sequence[Any]] = None) -> None:
        self._cursor.execute(query, params or ())

    def fetch_one(self, query: str, params: Optional[Sequence[Any]] = None) -> Optional[dict]:
        self.execute(query, params)
        return self._cursor.fetchone()

    def fetch_all(self, query: str, params: Optional[Sequence[Any]] = None) -> list[dict]:
        self.execute(query, params)
        return list(self._cursor.fetchall())

    # Transaction helpers -----------------------------------------------------
    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    # Cleanup -----------------------------------------------------------------
    def close(self) -> None:
        try:
            if not self._cursor.closed:
                self._cursor.close()
        finally:
            try:
                self._conn.rollback()
            except psycopg2.Error:
                pass
            self._pool.putconn(self._conn)


def db_session() -> DatabaseSession:
    """Utility for ad-hoc session creation outside of FastAPI dependencies."""
    return DatabaseSession()


def get_db() -> Iterable[DatabaseSession]:
    """FastAPI dependency that yields a database session."""
    db = DatabaseSession()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

