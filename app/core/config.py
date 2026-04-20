from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    
    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # Gemini API
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    # Application
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # LangSmith / tracing
    LANGSMITH_TRACING: bool = True
    LANGSMITH_API_KEY: str 
    LANGSMITH_PROJECT: str
    LANGSMITH_ENDPOINT: str
    
    # File upload
    MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 20 MB
    UPLOAD_DIR: str = "uploads"

    # Billing / Stripe
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRICE_LITE_ID: Optional[str] = None
    STRIPE_PRICE_FULL_ID: Optional[str] = None
    STRIPE_TOPUP_PRICE_ID: Optional[str] = None
    BILLING_PORTAL_RETURN_URL: str = "http://localhost:5173/app/billing"
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    TRIAL_DAYS: int = 14
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

