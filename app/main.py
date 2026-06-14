from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.logging_config import setup_logging
from app.core.config import settings

setup_logging()

app = FastAPI(
    title="Bot Platform API",
    description="Backend для платформы управления AI-ботами",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix= "/api/v1" if settings.LOCAL == 'true' else '/v1')


@app.get("/")
async def root():
    return {"message": "Bot Platform API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

