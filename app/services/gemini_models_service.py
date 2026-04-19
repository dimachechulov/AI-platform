"""Список чат-моделей Gemini через google-generativeai (list_models) с кешированием."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from app.core.config import settings

_DESCRIPTION_MAX_LEN = 140


def _ensure_genai_configured() -> None:
    genai.configure(api_key=settings.GEMINI_API_KEY)


def _short_model_id(full_name: str) -> str:
    """Имя для LangChain / graph: `models/gemini-pro` -> `gemini-pro`."""
    if full_name.startswith("models/"):
        return full_name[len("models/") :]
    return full_name


def _truncate_description(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip()
    if len(s) <= _DESCRIPTION_MAX_LEN:
        return s
    return s[: _DESCRIPTION_MAX_LEN - 1].rstrip() + "…"


@lru_cache(maxsize=1)
def list_chat_models_cached() -> tuple[dict[str, Any], ...]:
    """Модели с generateContent; кеш до перезапуска процесса."""
    _ensure_genai_configured()
    rows: List[Dict[str, Any]] = []
    for m in genai.list_models():
        methods = getattr(m, "supported_generation_methods", None) or []
        if "generateContent" not in methods:
            continue
        full = getattr(m, "name", "") or ""
        rows.append(
            {
                "name": _short_model_id(full),
                "display_name": getattr(m, "display_name", None),
                "description": _truncate_description(getattr(m, "description", None)),
            }
        )

    rows.sort(key=lambda r: (r.get("display_name") or r["name"]).lower())
    return tuple(rows)
