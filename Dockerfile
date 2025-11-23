FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
# RUN apt-get update && apt-get install -y \
#     gcc \
#     postgresql-client \
#     && rm -rf /var/lib/apt/lists/*

# Создание директории для pip cache
RUN mkdir -p /root/.cache/pip

# Копирование requirements
COPY requirements.txt .

# Установка uv (для быстрого управления зависимостями)
RUN pip install --no-cache-dir uv

# Установка зависимостей через uv (используется системный Python)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

# Копирование приложения
COPY . .

# Создание директории для загрузок
RUN mkdir -p uploads

# Создание директории для скриптов
RUN mkdir -p scripts

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Порт
EXPOSE 8000

# Скрипт запуска
COPY scripts/start.sh /start.sh
RUN chmod +x /start.sh

# Запуск приложения
CMD ["bash", "/start.sh"]

