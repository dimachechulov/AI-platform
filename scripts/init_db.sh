#!/bin/bash
# Скрипт для инициализации базы данных

echo "Waiting for database to be ready..."
python -c "
import sys
import time
from sqlalchemy import create_engine, text
from app.core.config import settings

max_retries = 30
retry_interval = 2

for i in range(max_retries):
    try:
        engine = create_engine(settings.DATABASE_URL.replace(f'/{settings.POSTGRES_DB}', '/postgres'))
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        print('Database is ready!')
        break
    except Exception as e:
        if i < max_retries - 1:
            print(f'Waiting for database... ({i+1}/{max_retries})')
            time.sleep(retry_interval)
        else:
            print(f'Database is not available: {e}')
            sys.exit(1)
"

echo "Creating database if not exists..."
python -m app.db.init_database

echo "Running Alembic migrations..."
alembic upgrade head

echo "Database initialization complete!"

