from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator

from app.api.dependencies import get_current_user
from app.db.database import DatabaseSession, get_db
from app.db.auth_repository import AuthRepository
from app.services.auth_service import AuthService

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
auth_service = AuthService(AuthRepository())


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str = None

    @field_validator("password")
    def validate_password_length(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be <= 72 bytes for bcrypt")
        return v


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str = None
    is_active: bool
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: int
    email: str
    full_name: str = None
    workspaces: list = []
    
    class Config:
        from_attributes = True


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: DatabaseSession = Depends(get_db)):
    """Регистрация нового пользователя"""
    return auth_service.register_user(
        db,
        email=user_data.email,
        password=user_data.password,
        full_name=user_data.full_name,
    )


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: DatabaseSession = Depends(get_db)):
    """Вход пользователя"""
    return auth_service.login_user(db, email=form_data.username, password=form_data.password)


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=Token)
async def refresh_token(payload: RefreshRequest, db: DatabaseSession = Depends(get_db)):
    """Обновление access токена по refresh токену."""
    return auth_service.refresh_tokens(db, payload.refresh_token)


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: Dict = Depends(get_current_user),
    db: DatabaseSession = Depends(get_db),
):
    """Получение профиля текущего пользователя"""
    return auth_service.build_user_profile(db, current_user)

