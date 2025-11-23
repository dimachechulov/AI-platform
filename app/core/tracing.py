"""
LangSmith tracing configuration utilities.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.tracers import LangChainTracer

from app.core.config import settings


def _configure_env() -> None:
    """Propagate LangSmith settings to environment variables for LangChain."""
    if settings.LANGSMITH_TRACING:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    if settings.LANGSMITH_API_KEY:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.LANGSMITH_API_KEY)
    if settings.LANGSMITH_PROJECT:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGSMITH_PROJECT)
    if settings.LANGSMITH_ENDPOINT:
        os.environ.setdefault("LANGCHAIN_ENDPOINT", settings.LANGSMITH_ENDPOINT)


_configure_env()


@lru_cache(maxsize=1)
def get_callback_manager() -> Optional[CallbackManager]:
    """Return LangSmith callback manager if tracing is enabled."""
    if not settings.LANGSMITH_TRACING:
        return None

    tracer = LangChainTracer(project_name=settings.LANGSMITH_PROJECT or "bot-platform")
    return CallbackManager([tracer])

