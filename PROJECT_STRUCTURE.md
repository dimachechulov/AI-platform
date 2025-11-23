# Структура проекта

```
.
├── app/                          # Основное приложение
│   ├── __init__.py
│   ├── main.py                   # Точка входа FastAPI
│   │
│   ├── api/                      # API endpoints
│   │   ├── __init__.py
│   │   ├── dependencies.py       # Зависимости (JWT, workspace проверки)
│   │   └── v1/
│   │       ├── __init__.py       # Роутер API v1
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── auth.py        # Аутентификация (регистрация, вход)
│   │           ├── workspaces.py  # Управление workspace
│   │           ├── bots.py        # Управление ботами
│   │           ├── documents.py   # Загрузка и управление документами
│   │           ├── api_tools.py   # Управление API инструментами
│   │           └── chat.py        # Чат с ботами
│   │
│   ├── core/                     # Основные настройки
│   │   ├── __init__.py
│   │   ├── config.py             # Конфигурация из .env
│   │   └── security.py           # JWT, хеширование паролей
│   │
│   ├── db/                       # База данных
│   │   ├── __init__.py
│   │   ├── database.py           # Подключение к БД, чистые SQL-сессии
│   │   ├── repositories.py       # Функции для CRUD-операций
│   │   ├── schema.py             # DDL-скрипт для инициализации
│   │   └── init_db.py            # Инициализация pgvector
│   │
│   └── services/                 # Бизнес-логика
│       ├── __init__.py
│       ├── document_processor.py        # Обработка PDF/DOCX/TXT
│       ├── document_processor_service.py # Фоновая обработка документов
│       ├── vector_store.py               # Векторизация и поиск
│       └── langchain_service.py          # LangChain Graph сервис
│
├── uploads/                      # Загруженные файлы
│   └── .gitkeep
│
├── .env.example                  # Пример конфигурации
├── .env                          # Ваша конфигурация (не в git)
├── .gitignore
├── .dockerignore
│
├── Dockerfile                    # Образ приложения
├── docker-compose.yml            # Docker Compose конфигурация
│
├── requirements.txt              # Python зависимости
│
├── README.md                     # Основная документация
├── QUICKSTART.md                 # Быстрый старт
└── PROJECT_STRUCTURE.md          # Этот файл
```

## Основные компоненты

### API Endpoints

- **auth.py**: Регистрация, вход, получение профиля
- **workspaces.py**: Создание и управление рабочими пространствами
- **bots.py**: CRUD операции для ботов, управление конфигурацией
- **documents.py**: Загрузка, обработка, удаление документов
- **api_tools.py**: Управление внешними API инструментами
- **chat.py**: Отправка сообщений боту, получение истории

### Сервисы

- **document_processor.py**: Извлечение текста из PDF/DOCX/TXT
- **vector_store.py**: Генерация embeddings и семантический поиск
- **langchain_service.py**: Построение LangChain Graph из конфига, обработка запросов

### Таблицы БД

- **User**: Пользователи
- **Workspace**: Рабочие пространства
- **Bot**: Боты с конфигурацией
- **Document**: Загруженные документы
- **DocumentChunk**: Фрагменты документов с embeddings
- **DocumentChunkEmbeddings**: Хранит вектора для поиска по pgvector
- **APITool**: Внешние API инструменты
- **ChatSession**: Сессии чата
- **ChatMessage**: Сообщения в чате

## Поток данных

1. **Регистрация/Вход** → JWT токен
2. **Создание бота** → Сохранение конфигурации в БД
3. **Загрузка документа** → Обработка → Векторизация → Сохранение chunks
4. **Создание API инструмента** → Сохранение конфигурации
5. **Отправка сообщения** → Построение Graph из конфига → Обработка через LangChain → Ответ

## Конфигурация бота

Конфигурация бота определяет структуру LangChain Graph:

```json
{
  "use_rag": true,           // Использовать RAG поиск
  "api_tool_ids": [1, 2],    // ID API инструментов
  "rag_settings": {}          // Дополнительные настройки RAG
}
```

На основе этой конфигурации `LangChainService.build_graph_from_config()` создает граф с соответствующими инструментами.

