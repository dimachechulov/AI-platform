from fastapi import APIRouter
from app.api.v1.endpoints import auth, billing, bots, documents, api_tools, chat, workspaces, audit, gemini_models, usage

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(bots.router, prefix="/bots", tags=["bots"])
api_router.include_router(gemini_models.router, prefix="/gemini", tags=["gemini"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(api_tools.router, prefix="/api-tools", tags=["api-tools"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(usage.router, prefix="/usage", tags=["usage"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])

