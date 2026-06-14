"""SQLAlchemy engine and session factory."""
from __future__ import annotations

from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def db_session() -> Session:
    """Create a session for use outside FastAPI (e.g. background tasks). Caller must close()."""
    return SessionLocal()


def set_session_user_id(session: Session, user_id: Optional[int]) -> None:
    """Set app.user_id for audit triggers (PostgreSQL SET LOCAL)."""
    if user_id is not None:
        session.execute(text("SET LOCAL app.user_id = :uid"), {"uid": str(user_id)})
    else:
        session.execute(text("SET LOCAL app.user_id = NULL"))


# Backwards-compatible alias for type hints in endpoints
DatabaseSession = Session
