from typing import Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_access_token
from app.db.database import DatabaseSession, get_db, set_session_user_id
from app.db.auth_repository import AuthRepository
from app.db.workspace_repository import WorkspaceRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
auth_repo = AuthRepository()
workspace_repo = WorkspaceRepository()


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

    user = auth_repo.get_user_by_email(db, email)
    if not user:
        raise credentials_exception

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    
    set_session_user_id(db, user["id"])

    return user


async def get_user_workspace(
    workspace_id: int,
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
) -> Dict:
    """Проверка доступа к рабочему пространству (только владелец)."""
    workspace = workspace_repo.get_workspace_for_owner(
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
    workspace = workspace_repo.check_user_workspace_access(
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

