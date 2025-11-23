from datetime import datetime, timedelta
from typing import Optional
import os
import hashlib
import hmac
import base64
import binascii
from jose import JWTError, jwt
from app.core.config import settings

PBKDF2_ITERATIONS = 150_000
SALT_LENGTH = 16


def _hash_password(password: str, salt: bytes) -> bytes:
    """Возвращает pbkdf2-hmac sha256 hash."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )


def get_password_hash(password: str) -> str:
    """Хеширование пароля с использованием PBKDF2 + SHA256."""
    salt = os.urandom(SALT_LENGTH)
    hashed = _hash_password(password, salt)
    return f"{base64.b64encode(salt).decode()}:{base64.b64encode(hashed).decode()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля."""
    try:
        salt_b64, hash_b64 = hashed_password.split(":")
        salt = base64.b64decode(salt_b64)
        stored_hash = base64.b64decode(hash_b64)
    except (ValueError, binascii.Error):
        return False
    computed_hash = _hash_password(plain_password, salt)
    return hmac.compare_digest(stored_hash, computed_hash)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создание JWT токена"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Декодирование JWT токена"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

