# Bot Platform Backend

Backend-приложение для платформы управления AI-ботами с использованием Gemini, LangChain и RAG.

## Функциональность

- ✅ Аутентификация и авторизация пользователей (JWT)
- ✅ Управление рабочими пространствами
- ✅ Создание и управление ботами с конфигурацией LangChain Graph
- ✅ Загрузка и обработка документов (PDF, DOCX, TXT) с векторизацией
- ✅ Настройка API-инструментов для подключения к внешним REST API
- ✅ Интерактивный чат с ботами через LangChain Graph
- ✅ Интеграция с Gemini AI

## Технологический стек

- **FastAPI** - веб-фреймворк
- **PostgreSQL + pgvector** - база данных с поддержкой векторного поиска
- **psycopg2 + чистый SQL** - работа с базой данных без ORM
- **LangChain + LangGraph** - построение графов для ботов
- **Gemini** - языковая модель и эмбеддинги
- **Docker** - контейнеризация

## Структура проекта

```
.
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   └── endpoints/
│   │   │       ├── auth.py          # Аутентификация
│   │   │       ├── bots.py          # Управление ботами
│   │   │       ├── documents.py     # Управление документами
│   │   │       ├── api_tools.py     # Управление API инструментами
│   │   │       └── chat.py          # Чат с ботами
│   │   └── dependencies.py          # Зависимости (JWT, workspace)
│   ├── core/
│   │   ├── config.py                # Конфигурация
│   │   └── security.py              # Безопасность (JWT, хеширование)
│   ├── db/
│   │   ├── database.py              # Подключение к БД и пул соединений
│   │   ├── repositories.py          # SQL-репозитории (CRUD)
│   │   └── schema.py                # SQL-схема приложения
│   ├── services/
│   │   ├── document_processor.py    # Обработка документов
│   │   ├── vector_store.py          # Векторизация и поиск
│   │   └── langchain_service.py     # LangChain Graph сервис
│   └── main.py                      # Точка входа
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Установка и запуск

### Предварительные требования

- Docker и Docker Compose
- Gemini API ключ (получить можно на https://makersuite.google.com/app/apikey)
- CLI для управления зависимостями: [uv](https://github.com/astral-sh/uv) (контейнер устанавливает его автоматически, для локальной разработки рекомендуется `pip install uv`)

### Шаги для запуска

1. **Клонируйте репозиторий** (если нужно)

2. **Создайте файл `.env`** на основе `.env.example`:

```bash
cp .env.example .env
```

3. **Отредактируйте `.env` файл** и укажите:
   - `GEMINI_API_KEY` - ваш API ключ Gemini
   - `GEMINI_MODEL` - модель Gemini (по умолчанию `gemini-1.5-flash`)
   - `SECRET_KEY` - секретный ключ для JWT (сгенерируйте случайную строку)
   - При необходимости измените настройки базы данных

4. **Запустите приложение через Docker Compose**:

```bash
docker-compose up -d
```

> Контейнер автоматически создаёт/обновляет папку `./venv` через `uv`. Первый прогон синхронизирует зависимости и дальше используются уже скачанные пакеты.

5. **Проверьте, что приложение запущено**:

```bash
curl http://localhost:8000/health
```

6. **Документация API доступна по адресу**:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## Использование API

### 1. Регистрация пользователя

```bash
POST /api/v1/auth/register
{
  "email": "user@example.com",
  "password": "secure_password",
  "full_name": "John Doe"
}
```

### 2. Вход

```bash
POST /api/v1/auth/login
{
  "username": "user@example.com",
  "password": "secure_password"
}
```

Ответ содержит `access_token`, который нужно использовать в заголовке `Authorization: Bearer <token>`

### 3. Создание бота

```bash
POST /api/v1/bots
Authorization: Bearer <token>
{
  "name": "My Bot",
  "workspace_id": 1,
  "system_prompt": "You are a helpful assistant.",
  "config": {
    "use_rag": true,
    "api_tool_ids": [],
    "rag_settings": {}
  },
  "temperature": "0.7",
  "max_tokens": 2048
}
```

### 4. Загрузка документа

```bash
POST /api/v1/documents?workspace_id=1
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <your_file.pdf>
```

### 5. Создание API инструмента

```bash
POST /api/v1/api-tools
Authorization: Bearer <token>
{
  "workspace_id": 1,
  "name": "Weather API",
  "description": "Get weather information",
  "url": "https://api.weather.com/v1/current",
  "method": "GET",
  "headers": {"Authorization": "Bearer token"},
  "params": {"city": "Moscow"}
}
```

### 6. Отправка сообщения боту

```bash
POST /api/v1/chat
Authorization: Bearer <token>
{
  "message": "Hello, bot!",
  "bot_id": 1
}
```

## Конфигурация бота

Конфигурация бота (`config`) задаёт полноценный граф из нескольких узлов. Каждый узел описывает:

- `system_prompt` — локальный контекст.
- `use_rag` + `allowed_document_ids` — какие документы можно читать.
- `api_tool_ids` — какие API-инструменты разрешены.
- `transitions` — правила перехода к следующим узлам (например, по ключевому слову в ответе).

Пример:

```json
{
  "entry_node_id": "greeting",
  "nodes": [
    {
      "id": "greeting",
      "name": "Greeting",
      "system_prompt": "Ты дружелюбный ассистент.",
      "use_rag": false,
      "api_tool_ids": [],
      "transitions": [
        {"target_node_id": "research", "condition": {"type": "keyword", "value": "doc"}}
      ]
    },
    {
      "id": "research",
      "name": "RAG stage",
      "system_prompt": "Отвечай, опираясь на документы.",
      "use_rag": true,
      "allowed_document_ids": [12, 15],
      "api_tool_ids": [3],
      "transitions": []
    }
  ]
}
```

`LangChainService` превращает такой JSON в LangGraph: каждый узел вызывает LLM с собственным набором инструментов, а переходы управляют дальнейшим потоком.

## Трасировка (LangSmith)

Включите трейсинг LangSmith, если нужно отслеживать цепочки LangChain:

1. Добавьте в `.env`:
   ```
   LANGSMITH_TRACING=true
   LANGSMITH_API_KEY=sk-...
   LANGSMITH_PROJECT=bot-platform-dev
   LANGSMITH_ENDPOINT=https://api.smith.langchain.com  # опционально
   ```
2. После рестарта приложения все вызовы LLM будут автоматически отправляться в LangSmith.

## Логирование

Логгер настраивается через модуль `app/core/logging_config.py` и активируется при запуске приложения. Уровень логов задаётся переменной окружения `LOG_LEVEL` (по умолчанию `INFO`). Чтобы писать логи в любом месте кода:

```python
import logging

logger = logging.getLogger(__name__)

def some_service_function():
    logger.info("Starting heavy job")
    try:
        ...
    except Exception:
        logger.exception("Job failed")
```

Uvicorn и FastAPI автоматически используют тот же конфиг, поэтому и системные, и пользовательские сообщения будут иметь единый формат `LEVEL | timestamp | logger | message`.

## База данных

При первом запуске:
1. Автоматически создается база данных (если не существует)
2. Включается расширение `pgvector`
3. Выполняются DDL-операторы из `app/db/schema.py`

### Обновление схемы

Проект больше не использует Alembic. Чтобы изменить структуру БД:

1. Обновите `app/db/schema.py`, добавив нужные `CREATE/ALTER`-запросы.
2. Запустите `docker-compose exec app python -m app.db.init_database`.
3. При необходимости выполните дополнительные SQL-скрипты вручную (например,
   для миграции данных).

## Обработка документов

Документы обрабатываются асинхронно:
1. Файл сохраняется на диск
2. Текст извлекается (PDF/DOCX/TXT)
3. Текст разбивается на chunks
4. Генерируются векторные представления (embeddings)
5. Сохраняются в БД

Статус обработки можно отслеживать через API: `GET /api/v1/documents/{document_id}`

## Безопасность

- Пароли хешируются с использованием bcrypt
- JWT токены для аутентификации
- Изоляция данных по workspace (каждый пользователь видит только свои данные)
- Валидация входных данных через Pydantic

## Производительность

- Асинхронная обработка документов
- Векторный поиск через pgvector
- Кэширование embeddings
- Оптимизированные запросы к БД

## Разработка

Для разработки с hot-reload:

```bash
docker-compose up
```

Изменения в коде будут автоматически применяться благодаря volume mount.

## Логирование

Логи доступны через:

```bash
docker-compose logs -f app
```

## Остановка

```bash
docker-compose down
```

Для удаления всех данных (включая БД):

```bash
docker-compose down -v
```

## Troubleshooting

### Проблема с подключением к БД

Убедитесь, что контейнер БД запущен и здоров:
```bash
docker-compose ps
docker-compose logs db
```

### Проблема с Gemini API

Проверьте, что `GEMINI_API_KEY` правильно указан в `.env` файле.

### Проблема с векторизацией

При первом запуске Sentence Transformers загружает модель (~80MB). Это может занять время.

## Лицензия

MIT

