from __future__ import annotations

from typing import Dict

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_password_reset_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)
from app.db.database import DatabaseSession
from app.db.auth_repository import AuthRepository
from app.services.email_service import EmailService


class AuthService:
    def __init__(self, repository: AuthRepository, email_service: EmailService | None = None):
        self.repository = repository
        self.email_service = email_service or EmailService()

    def register_user(self, db: DatabaseSession, *, email: str, password: str, full_name: str | None) -> dict:
        existing_user = self.repository.get_user_by_email(db, email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        hashed_password = get_password_hash(password)
        new_user = self.repository.create_user(
            db,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
        )
        self.repository.create_workspace(db, owner_id=new_user["id"], name="My Workspace")
        db.commit()
        return new_user

    def login_user(self, db: DatabaseSession, *, email: str, password: str) -> dict:
        user = self.repository.get_user_by_email(db, email)
        if not user or not verify_password(password, user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )
        return self._issue_tokens(user)

    def refresh_tokens(self, db: DatabaseSession, refresh_token: str) -> dict:
        refresh_payload = decode_refresh_token(refresh_token)
        if not refresh_payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        email = refresh_payload.get("sub")
        user_id = refresh_payload.get("user_id")
        if not email or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = self.repository.get_user_by_email(db, email)
        if not user or user["id"] != user_id or not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return self._issue_tokens(user)

    def build_user_profile(self, db: DatabaseSession, current_user: Dict) -> dict:
        workspaces = self.repository.list_workspaces_for_owner(db, current_user["id"])
        return {
            "id": current_user["id"],
            "email": current_user["email"],
            "full_name": current_user.get("full_name"),
            "workspaces": [{"id": w["id"], "name": w["name"]} for w in workspaces],
        }

    async def request_password_reset(self, db: DatabaseSession, *, email: str) -> dict:
        user = self.repository.get_user_by_email(db, email)
        if user and user.get("is_active", True):
            token = create_password_reset_token(
                data={"sub": user["email"], "user_id": user["id"]}
            )
            reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?token={token}"
            await self.email_service.send_password_reset_email(
                to_email=user["email"],
                reset_url=reset_url,
            )
        return {"message": "Мы отправили ссылку для сброса пароля"}

    def reset_password(self, db: DatabaseSession, *, token: str, new_password: str) -> dict:
        payload = decode_password_reset_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Недействительная или просроченная ссылка для сброса пароля",
            )
        email = payload.get("sub")
        user_id = payload.get("user_id")
        if not email or not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Недействительная или просроченная ссылка для сброса пароля",
            )
        user = self.repository.get_user_by_email(db, email)
        if not user or user["id"] != user_id or not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Недействительная или просроченная ссылка для сброса пароля",
            )
        hashed_password = get_password_hash(new_password)
        self.repository.update_user_password(
            db,
            user_id=user["id"],
            hashed_password=hashed_password,
        )
        db.commit()
        return {"message": "Пароль успешно изменён"}

    @staticmethod
    def _issue_tokens(user: dict) -> dict:
        access_token = create_access_token(data={"sub": user["email"], "user_id": user["id"]})
        refresh_token = create_refresh_token(data={"sub": user["email"], "user_id": user["id"]})
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
