"""
Скрипт для инициализации расширения pgvector без SQLAlchemy.
"""
import psycopg2

from app.core.config import settings


def init_pgvector() -> None:
    """Ensure pgvector extension exists in the target database."""
    with psycopg2.connect(settings.DATABASE_URL) as conn:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    print("pgvector extension initialized")


if __name__ == "__main__":
    init_pgvector()

