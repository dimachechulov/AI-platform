# Быстрый старт

## Шаг 1: Получение Gemini API ключа

1. Перейдите на https://makersuite.google.com/app/apikey
2. Войдите в свой Google аккаунт
3. Создайте новый API ключ
4. Скопируйте ключ

## Шаг 2: Настройка окружения

1. Скопируйте `.env.example` в `.env`:
```bash
cp .env.example .env
```

2. Откройте `.env` и укажите:
   - `GEMINI_API_KEY` - ваш API ключ Gemini
   - `SECRET_KEY` - случайная строка для JWT (можно сгенерировать: `openssl rand -hex 32`)
   - (Опционально) установите [uv](https://github.com/astral-sh/uv) локально: `pip install uv` и устанавливайте зависимости через `uv pip install -r requirements.txt`

> При запуске `docker-compose up` контейнер автоматически создаёт/обновляет папку `./venv` и синхронизирует зависимости через `uv`, так что повторные сборки не скачивают пакеты заново.

## Шаг 3: Запуск

```bash
docker-compose up -d
```

Приложение будет доступно по адресу: http://localhost:8000

## Шаг 4: Проверка работы

```bash
# Проверка здоровья
curl http://localhost:8000/health

# Документация API
# Откройте в браузере: http://localhost:8000/docs
```

## Шаг 5: Регистрация и создание бота

### 1. Регистрация пользователя

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpassword123",
    "full_name": "Test User"
  }'
```

### 2. Вход

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=testpassword123"
```

Сохраните `access_token` из ответа.

### 3. Получение workspace

```bash
curl -X GET "http://localhost:8000/api/v1/workspaces" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Сохраните `id` workspace (обычно это 1 для первого workspace).

### 4. Создание бота

```bash
curl -X POST "http://localhost:8000/api/v1/bots" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Bot",
    "workspace_id": 1,
    "system_prompt": "You are a helpful assistant that answers questions based on provided documents.",
    "config": {
      "use_rag": true,
      "api_tool_ids": [],
      "rag_settings": {}
    },
    "temperature": "0.7",
    "max_tokens": 2048
  }'
```

### 5. Загрузка документа (опционально)

```bash
curl -X POST "http://localhost:8000/api/v1/documents?workspace_id=1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/your/document.pdf"
```

### 6. Отправка сообщения боту

```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello! What can you help me with?",
    "bot_id": 1
  }'
```

## Остановка

```bash
docker-compose down
```

Для полной очистки (включая данные БД):

```bash
docker-compose down -v
```

## Troubleshooting

### Проблема: "Could not initialize pgvector extension"

Это нормально при первом запуске. Расширение будет создано автоматически при первом запросе к БД.

### Проблема: "GEMINI_API_KEY not found"

Убедитесь, что вы указали `GEMINI_API_KEY` в файле `.env` и перезапустили контейнеры.

### Проблема: Документы не обрабатываются

Проверьте логи:
```bash
docker-compose logs app
```

Убедитесь, что файл был загружен и имеет правильный формат (PDF, DOCX или TXT).

