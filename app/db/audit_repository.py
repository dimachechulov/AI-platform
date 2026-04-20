from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models as m


class AuditRepository:
    def list_audit_logs(
        self,
        db: Session,
        *,
        user_id: Optional[int],
        table_name: Optional[str],
        action: Optional[str],
        limit: int,
        offset: int,
    ) -> list[dict]:
        stmt = (
            select(m.AuditLog, m.User.email.label("user_email"), m.User.full_name.label("user_name"))
            .select_from(m.AuditLog)
            .outerjoin(m.User, m.User.id == m.AuditLog.user_id)
            .order_by(m.AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if user_id:
            stmt = stmt.where(m.AuditLog.user_id == user_id)
        if table_name:
            stmt = stmt.where(m.AuditLog.table_name == table_name)
        if action:
            stmt = stmt.where(m.AuditLog.action == action)
        out = []
        for audit_log, email, name in db.execute(stmt):
            out.append(
                {
                    "id": audit_log.id,
                    "user_id": audit_log.user_id,
                    "action": audit_log.action,
                    "table_name": audit_log.table_name,
                    "record_id": audit_log.record_id,
                    "old_data": audit_log.old_data,
                    "new_data": audit_log.new_data,
                    "ip_address": audit_log.ip_address,
                    "user_agent": audit_log.user_agent,
                    "created_at": audit_log.created_at,
                    "user_email": email,
                    "user_name": name,
                }
            )
        return out

    def count_audit_logs(
        self,
        db: Session,
        *,
        user_id: Optional[int],
        table_name: Optional[str],
        action: Optional[str],
    ) -> int:
        stmt = select(func.count()).select_from(m.AuditLog)
        if user_id:
            stmt = stmt.where(m.AuditLog.user_id == user_id)
        if table_name:
            stmt = stmt.where(m.AuditLog.table_name == table_name)
        if action:
            stmt = stmt.where(m.AuditLog.action == action)
        return int(db.scalar(stmt) or 0)

    def get_audit_log_by_id(self, db: Session, log_id: int) -> Optional[dict]:
        row = db.execute(
            select(m.AuditLog, m.User.email.label("user_email"), m.User.full_name.label("user_name"))
            .select_from(m.AuditLog)
            .outerjoin(m.User, m.User.id == m.AuditLog.user_id)
            .where(m.AuditLog.id == log_id)
        ).first()
        if not row:
            return None
        audit_log, email, name = row
        return {
            "id": audit_log.id,
            "user_id": audit_log.user_id,
            "action": audit_log.action,
            "table_name": audit_log.table_name,
            "record_id": audit_log.record_id,
            "old_data": audit_log.old_data,
            "new_data": audit_log.new_data,
            "ip_address": audit_log.ip_address,
            "user_agent": audit_log.user_agent,
            "created_at": audit_log.created_at,
            "user_email": email,
            "user_name": name,
        }
