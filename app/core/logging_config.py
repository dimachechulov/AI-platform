import logging
import logging.config
from typing import Dict, Any

from app.core.config import settings


def _build_logging_config() -> Dict[str, Any]:
    """Return logging configuration dict."""
    level = settings.LOG_LEVEL.upper()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(levelname)s | %(asctime)s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": level,
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {  # root logger
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "psycopg2": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }


def setup_logging() -> None:
    """Configure application-wide logging."""
    logging.config.dictConfig(_build_logging_config())
    logging.getLogger(__name__).debug("Logging configured with level %s", settings.LOG_LEVEL)

