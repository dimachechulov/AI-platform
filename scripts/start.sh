#!/bin/bash
set -e

echo "Starting application..."

# Проверяем наличие uv
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required but not installed. Exiting."
    exit 1
fi

SYSTEM_SYNC_MARKER="/.uv-system-synced"
VENV_PATH="/app/venv"
VENV_PYTHON="$VENV_PATH/bin/python"
VENV_MARKER="$VENV_PATH/.uv-synced"

# Создаем venv, если директория смонтирована, но окружение отсутствует
if [ -d "$VENV_PATH" ] && [ ! -f "$VENV_PYTHON" ]; then
    echo "Virtual environment not found. Creating via uv..."
    if ! uv venv "$VENV_PATH"; then
        echo "Failed to create virtual environment. Will use system Python."
    fi
fi

# Активация venv если он существует и совместим
if [ -f "$VENV_PATH/bin/activate" ] && [ -f "$VENV_PYTHON" ]; then
    echo "Activating virtual environment..."
    if ! source "$VENV_PATH/bin/activate"; then
        echo "Unable to activate venv, falling back to system Python"
    else
        echo "Using venv Python: $("$VENV_PYTHON" --version)"
        if [ ! -f "$VENV_MARKER" ]; then
            echo "Syncing dependencies into venv via uv..."
            uv pip install --python "$VENV_PYTHON" -r /app/requirements.txt
            touch "$VENV_MARKER"
        fi
    fi
else
    echo "No usable venv found, relying on system Python packages"
    if [ ! -f "$SYSTEM_SYNC_MARKER" ]; then
        echo "Ensuring system dependencies are synced via uv..."
        uv pip install --system -r /app/requirements.txt
        touch "$SYSTEM_SYNC_MARKER"
    fi
fi

PYTHON_CMD="$(command -v python)"

# Создаем БД и применяем схему
echo "Preparing database schema..."
$PYTHON_CMD -m app.db.init_database

# Запускаем приложение
echo "Starting FastAPI application..."

# Автоперезапуск Uvicorn при изменениях в dev-режиме
EXTRA_UVICORN_ARGS=""
DEBUG_LOWER="$(printf '%s' "${DEBUG:-}" | tr '[:upper:]' '[:lower:]')"
RELOAD_FLAG="$(printf '%s' "${UVICORN_RELOAD:-}" | tr '[:upper:]' '[:lower:]')"

if [ "$DEBUG_LOWER" = "true" ] || [ "$RELOAD_FLAG" = "true" ]; then
    echo "Uvicorn autoreload enabled (DEBUG=$DEBUG_LOWER, UVICORN_RELOAD=$RELOAD_FLAG)"
    EXTRA_UVICORN_ARGS="--reload --reload-dir /app"
fi

exec "$PYTHON_CMD" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 $EXTRA_UVICORN_ARGS

