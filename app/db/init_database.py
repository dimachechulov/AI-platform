"""
Инициализация базы данных без Alembic/SQLAlchemy.

1. Ожидает доступности Postgres
2. Создает базу данных при отсутствии
3. Гарантирует наличие расширения pgvector
4. Применяет SQL-схему приложения
"""
from __future__ import annotations

import sys
import time
from typing import Dict
from urllib.parse import urlparse

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from app.core.config import settings
from app.db import schema


def _parse_db_url(url: str) -> Dict[str, str]:
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or settings.POSTGRES_USER,
        "password": parsed.password or settings.POSTGRES_PASSWORD,
        "database": (parsed.path or "/").lstrip("/") or settings.POSTGRES_DB,
    }


DB_PARAMS = _parse_db_url(settings.DATABASE_URL)


def _connect(database: str):
    params = DB_PARAMS.copy()
    params["database"] = database
    return psycopg2.connect(**params)


def wait_for_db(max_retries: int = 30, retry_interval: int = 2) -> bool:
    """Ожидание доступности сервера Postgres."""
    for attempt in range(max_retries):
        try:
            with _connect("postgres") as conn:
                conn.autocommit = True
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            print("Database server is ready!")
            return True
        except psycopg2.OperationalError as exc:
            if attempt < max_retries - 1:
                print(f"Waiting for database... ({attempt + 1}/{max_retries})")
                time.sleep(retry_interval)
            else:
                print(f"Database is not available: {exc}")
                return False
    return False


def create_database_if_not_exists() -> bool:
    """Создает основную БД если она отсутствует."""
    db_name = DB_PARAMS["database"]
    try:
        with _connect("postgres") as conn:
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
                exists = cursor.fetchone()
                if not exists:
                    print(f"Creating database {db_name}...")
                    cursor.execute(f'CREATE DATABASE "{db_name}"')
                    print(f"Database {db_name} created successfully")
                else:
                    print(f"Database {db_name} already exists")
        return True
    except Exception as exc:
        print(f"Error creating database: {exc}")
        return False


def init_pgvector() -> bool:
    """Включает расширение pgvector в целевой БД."""
    try:
        with _connect(DB_PARAMS["database"]) as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        print("pgvector extension initialized")
        return True
    except Exception as exc:
        print(f"Warning: Could not initialize pgvector extension: {exc}")
        return False


def apply_app_schema() -> bool:
    """Применяет SQL-схему приложения."""
    try:
        with _connect(DB_PARAMS["database"]) as conn:
            schema.apply_schema(conn)
        print("Database schema ensured successfully")
        return True
    except Exception as exc:
        print(f"Error applying schema: {exc}")
        return False


if __name__ == "__main__":
    print("Initializing database...")

    if not wait_for_db():
        sys.exit(1)

    if not create_database_if_not_exists():
        sys.exit(1)

    init_pgvector()

    if not apply_app_schema():
        sys.exit(1)

    print("Database initialization complete!")
