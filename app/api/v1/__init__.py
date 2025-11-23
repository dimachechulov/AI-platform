from fastapi import APIRouter
from app.api.v1.endpoints import auth, bots, documents, api_tools, chat, workspaces

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(bots.router, prefix="/bots", tags=["bots"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(api_tools.router, prefix="/api-tools", tags=["api-tools"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])

