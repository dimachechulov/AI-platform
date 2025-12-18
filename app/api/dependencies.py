from typing import Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_access_token
from app.db import repositories as repo
from app.db.database import DatabaseSession, get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: DatabaseSession = Depends(get_db),
) -> Dict:
    """Получение текущего пользователя из JWT токена."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    email: Optional[str] = payload.get("sub") if isinstance(payload, dict) else None
    if not email:
        raise credentials_exception

    user = repo.get_user_by_email(db, email)
    if not user:
        raise credentials_exception

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    
    # Set user_id in session for audit logging
    db.set_user_id(user["id"])

    return user


async def get_user_workspace(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
) -> Dict:
    """Проверка доступа к рабочему пространству (только владелец)."""
    workspace = repo.get_workspace_for_owner(
        db,
        workspace_id=workspace_id,
        owner_id=current_user["id"],
    )

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    return workspace


async def check_workspace_access(
    workspace_id: int,
    current_user: Dict,
    db: DatabaseSession,
) -> Dict:
    """Проверка доступа к рабочему пространству (владелец или участник)."""
    workspace = repo.check_user_workspace_access(
        db,
        workspace_id=workspace_id,
        user_id=current_user["id"],
    )

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    return workspace

