#!/bin/bash
set -e

echo "Starting application..."


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

exec "$PYTHON_CMD" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 $EXTRA_UVICORN_ARGS --workers 4

