"""
Audit logs endpoints
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_current_user
from app.db import repositories as repo
from app.db.database import DatabaseSession, get_db

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
async def list_audit_logs(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    table_name: Optional[str] = Query(None, description="Filter by table name"),
    action: Optional[str] = Query(None, description="Filter by action (INSERT, UPDATE, DELETE)"),
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """
    Получить список логов аудита.
    Доступно только авторизованным пользователям.
    """
    logs = repo.list_audit_logs(
        db,
        user_id=user_id,
        table_name=table_name,
        action=action,
        limit=limit,
        offset=offset,
    )
    
    total = repo.count_audit_logs(
        db,
        user_id=user_id,
        table_name=table_name,
        action=action,
    )
    
    return {
        "logs": logs,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/logs/{log_id}")
async def get_audit_log(
    log_id: int,
    current_user: dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """
    Получить конкретный лог аудита по ID.
    """
    log = repo.get_audit_log_by_id(db, log_id)
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
        )
    
    return log

