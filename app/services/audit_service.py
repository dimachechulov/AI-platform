from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status

from app.db.database import DatabaseSession
from app.db.audit_repository import AuditRepository


class AuditService:
    def __init__(self, repository: AuditRepository):
        self.repository = repository

    def list_audit_logs(
        self,
        db: DatabaseSession,
        *,
        user_id: Optional[int],
        table_name: Optional[str],
        action: Optional[str],
        limit: int,
        offset: int,
    ) -> dict:
        logs = self.repository.list_audit_logs(
            db,
            user_id=user_id,
            table_name=table_name,
            action=action,
            limit=limit,
            offset=offset,
        )
        total = self.repository.count_audit_logs(
            db,
            user_id=user_id,
            table_name=table_name,
            action=action,
        )
        return {"logs": logs, "total": total, "limit": limit, "offset": offset}

    def get_audit_log(self, db: DatabaseSession, log_id: int) -> dict:
        log = self.repository.get_audit_log_by_id(db, log_id)
        if log:
            return log
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
        )
