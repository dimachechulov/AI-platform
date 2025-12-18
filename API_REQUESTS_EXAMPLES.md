# Примеры API запросов для бота магазина

Этот документ содержит все необходимые запросы для создания и использования бота магазина с routing нодой и специализированными нодами.

## Предварительные требования

1. **Запустить Appointments API** (см. раздел "Запуск Appointments API")
2. Получить токен авторизации (см. раздел "Авторизация")
3. Создать workspace
4. Загрузить документы для RAG
5. Создать API tools для внешних сервисов
6. Создать бота с графом нод

---

## Запуск Appointments API

Appointments API находится в соседней папке `appointments-api`. Это простой сервис для управления записями.

### Быстрый запуск

```bash
cd ../appointments-api
docker-compose up -d
```

API будет доступен по адресу `http://localhost:8001`

### Эндпоинты Appointments API

- `GET /slots` - Получение свободных временных окон
  - Параметры: `date` (опционально), `service_type` (опционально)
- `POST /book` - Создание записи
  - Тело запроса: `service_type`, `slot_id`, `customer_name`, `customer_phone`, `customer_email`
- `GET /health` - Проверка здоровья сервиса

Подробнее см. `../appointments-api/README.md`

---

## 1. Авторизация

### Регистрация пользователя
```bash
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secure_password_123",
  "full_name": "Иван Иванов"
}
```

### Вход в систему
```bash
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded

username=user@example.com&password=secure_password_123
```

**Ответ:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Сохраните `access_token` для последующих запросов.

---

## 2. Создание Workspace

```bash
POST /api/v1/workspaces
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "name": "Магазин электроники"
}
```

**Ответ:**
```json
{
  "id": 1,
  "name": "Магазин электроники",
  "owner_id": 1,
  "created_at": "2024-01-15T10:00:00Z"
}
```

Сохраните `id` workspace (в примере: `1`).

---

## 3. Загрузка документов для RAG

### Загрузка каталога продуктов
```bash
POST /api/v1/documents?workspace_id=1
Authorization: Bearer <your_token>
Content-Type: multipart/form-data

file: @test_data/products_catalog.txt
```

### Загрузка информации о записи
```bash
POST /api/v1/documents?workspace_id=1
Authorization: Bearer <your_token>
Content-Type: multipart/form-data

file: @test_data/appointments_info.txt
```

**Ответ:**
```json
{
  "id": 1,
  "filename": "products_catalog.txt",
  "file_size": 4523,
  "file_type": "txt",
  "status": "processing",
  "created_at": "2024-01-15T10:05:00Z"
}
```

**Важно:** Дождитесь обработки документов (статус `processed`). Проверьте статус:

```bash
GET /api/v1/documents/1
Authorization: Bearer <your_token>
```

Сохраните `id` документов (в примере: `1` для каталога, `2` для информации о записи).

---

## 4. Создание API Tools

### API для получения свободных окон (GET запрос)
```bash
POST /api/v1/api-tools
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "workspace_id": 1,
  "name": "get_available_slots",
  "description": "Получить список свободных временных окон для записи. Принимает параметр date в формате YYYY-MM-DD.",
  "url": "http://localhost:8001/slots",
  "method": "GET",
  "headers": {
    "Content-Type": "application/json"
  },
  "params": {},
  "body_schema": {}
}
```

**Примечание:** URL указывает на локальный сервис appointments API. Если API запущен в Docker, используйте `http://appointments_api:8001/slots` или настройте правильный URL в зависимости от вашей инфраструктуры.

**Ответ:**
```json
{
  "id": 1,
  "workspace_id": 1,
  "name": "get_available_slots",
  "description": "Получить список свободных временных окон для записи...",
  "url": "https://api.example.com/appointments/slots",
  "method": "GET",
  "headers": {...},
  "params": {},
  "body_schema": {},
  "created_at": "2024-01-15T10:10:00Z"
}
```

### API для записи (POST запрос)
```bash
POST /api/v1/api-tools
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "workspace_id": 1,
  "name": "book_appointment",
  "description": "Создать запись на консультацию или услугу. Требует параметры: service_type (тип услуги), slot_id (ID временного слота), customer_name (имя клиента), customer_phone (телефон клиента), customer_email (email клиента).",
  "url": "http://localhost:8001/book",
  "method": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "params": {},
  "body_schema": {
    "service_type": "consultation",
    "slot_id": 0,
    "customer_name": "",
    "customer_phone": "",
    "customer_email": ""
  }
}
```

**Примечание:** URL указывает на локальный сервис appointments API. Если API запущен в Docker, используйте `http://appointments_api:8001/book` или настройте правильный URL в зависимости от вашей инфраструктуры.

**Ответ:**
```json
{
  "id": 2,
  "workspace_id": 1,
  "name": "book_appointment",
  "description": "Создать запись на консультацию...",
  "url": "https://api.example.com/appointments/book",
  "method": "POST",
  "headers": {...},
  "params": {},
  "body_schema": {...},
  "created_at": "2024-01-15T10:12:00Z"
}
```

Сохраните `id` API tools (в примере: `1` для получения слотов, `2` для записи).

---

## 5. Создание бота с графом нод

```bash
POST /api/v1/bots
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "name": "Бот магазина",
  "workspace_id": 1,
  "system_prompt": "Ты - дружелюбный помощник магазина электроники. Помогай клиентам с выбором товаров, записью на консультации и отвечай на общие вопросы.",
  "temperature": "0.7",
  "max_tokens": 2048,
  "graph": {
    "entry_node_id": "routing",
    "nodes": [
      {
        "id": "routing",
        "name": "Routing Node",
        "system_prompt": "Ты - маршрутизатор для бота магазина. Анализируй запрос пользователя и определяй, к какому узлу его направить:\n- product_info: вопросы о товарах, ценах, характеристиках, наличии\n- available_slots: запросы о свободных временных окнах для записи\n- book_appointment: запросы на создание записи, бронирование времени\n- general: все остальные вопросы, общая информация о магазине\n\nОтвечай только ID узла.",
        "use_rag": false,
        "api_tool_ids": [],
        "allowed_document_ids": [],
        "transitions": [
          {
            "target_node_id": "product_info",
            "condition": {
              "type": "llm_routing"
            }
          },
          {
            "target_node_id": "available_slots",
            "condition": {
              "type": "llm_routing"
            }
          },
          {
            "target_node_id": "book_appointment",
            "condition": {
              "type": "llm_routing"
            }
          },
          {
            "target_node_id": "general",
            "condition": {
              "type": "llm_routing"
            }
          }
        ]
      },
      {
        "id": "product_info",
        "name": "Информация о продуктах",
        "system_prompt": "Ты - консультант по товарам магазина. Отвечай на вопросы о товарах, используя информацию из каталога. Будь точным в ценах и характеристиках. Если информации нет в каталоге, честно скажи об этом.",
        "use_rag": true,
        "api_tool_ids": [],
        "allowed_document_ids": [1],
        "transitions": []
      },
        {
          "id": "available_slots",
          "name": "Получение свободных окон",
          "system_prompt": "Ты помогаешь клиентам узнать о свободных временных окнах для записи. ВАЖНО: Для получения информации о доступных слотах ТЫ ДОЛЖЕН вызвать инструмент get_available_slots. НЕ пиши код Python, НЕ пиши примеры кода - просто вызови инструмент в формате JSON. Если пользователь не указал дату, используй сегодняшнюю дату или спроси у пользователя.",
          "use_rag": false,
          "api_tool_ids": [1],
          "allowed_document_ids": [],
          "transitions": []
        },
        {
          "id": "book_appointment",
          "name": "Запись на консультацию",
          "system_prompt": "Ты помогаешь клиентам записаться на консультацию или услугу. Собери всю необходимую информацию: тип услуги, желаемое время, контактные данные (имя, телефон, email). ВАЖНО: Для создания записи ТЫ ДОЛЖЕН вызвать инструмент book_appointment в формате JSON. НЕ пиши код Python, НЕ пиши примеры кода - просто вызови инструмент. После успешного вызова инструмента подтверди клиенту успешную запись.",
          "use_rag": false,
          "api_tool_ids": [2],
          "allowed_document_ids": [],
          "transitions": []
        },
      {
        "id": "general",
        "name": "Общие вопросы",
        "system_prompt": "Ты отвечаешь на общие вопросы о магазине: режим работы, адрес, способы оплаты, доставка, возврат товаров. Используй информацию из документов, если она доступна.",
        "use_rag": true,
        "api_tool_ids": [],
        "allowed_document_ids": [2, 3],
        "transitions": []
      }
    ]
  }
}
```

**Ответ:**
```json
{
  "id": 1,
  "name": "Бот магазина",
  "workspace_id": 1,
  "system_prompt": "Ты - дружелюбный помощник магазина...",
  "config": {...},
  "temperature": "0.7",
  "max_tokens": 2048,
  "created_at": "2024-01-15T10:15:00Z"
}
```

Сохраните `id` бота (в примере: `1`).

---

## 6. Использование бота

### Отправка сообщения боту
```bash
POST /api/v1/chat
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "message": "Какая цена на смартфон Galaxy Pro?",
  "bot_id": 1
}
```

**Ответ:**
```json
{
  "session_id": 1,
  "message": {
    "id": 1,
    "role": "assistant",
    "content": "Смартфон Galaxy Pro 2024 стоит 45,990 рублей. Он оснащен экраном 6.7 дюймов AMOLED с частотой обновления 120 Гц, процессором Snapdragon 8 Gen 3, 256 ГБ памяти и 12 ГБ ОЗУ...",
    "metadata": null,
    "created_at": "2024-01-15T10:20:00Z"
  },
  "metadata": null
}
```

### Примеры запросов для разных нод

#### Запрос информации о продукте (будет перенаправлен в product_info)
```bash
POST /api/v1/chat
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "message": "Расскажи про ноутбук UltraBook X1",
  "bot_id": 1,
  "session_id": 1
}
```

#### Запрос свободных окон (будет перенаправлен в available_slots)
```bash
POST /api/v1/chat
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "message": "Какие есть свободные окна на завтра?",
  "bot_id": 1,
  "session_id": 1
}
```

#### Запрос на запись (будет перенаправлен в book_appointment)
```bash
POST /api/v1/chat
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "message": "Хочу записаться на консультацию по выбору техники на завтра в 14:00. Меня зовут Иван, телефон +7 999 123-45-67, email ivan@example.com",
  "bot_id": 1,
  "session_id": 1
}
```

#### Общий вопрос (будет перенаправлен в general)
```bash
POST /api/v1/chat
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "message": "Какой у вас режим работы?",
  "bot_id": 1,
  "session_id": 1
}
```

---

## 7. Получение истории сообщений

```bash
GET /api/v1/chat/sessions/1/messages
Authorization: Bearer <your_token>
```

**Ответ:**
```json
[
  {
    "id": 1,
    "role": "user",
    "content": "Какая цена на смартфон Galaxy Pro?",
    "metadata": null,
    "created_at": "2024-01-15T10:20:00Z"
  },
  {
    "id": 2,
    "role": "assistant",
    "content": "Смартфон Galaxy Pro 2024 стоит 45,990 рублей...",
    "metadata": null,
    "created_at": "2024-01-15T10:20:05Z"
  }
]
```

---

## 8. Получение списка сессий

```bash
GET /api/v1/chat/sessions?bot_id=1
Authorization: Bearer <your_token>
```

**Ответ:**
```json
[
  {
    "id": 1,
    "bot_id": 1,
    "created_at": "2024-01-15T10:20:00Z"
  }
]
```

---

## Примечания

1. **Routing нода**: Использует LLM для анализа запроса пользователя и автоматического определения следующей ноды. Не требует явных ключевых слов.

2. **RAG ноды**: Ноды `product_info` и `general` используют RAG для поиска информации в загруженных документах.

3. **API Tools**: Ноды `available_slots` и `book_appointment` используют внешние API для получения данных и создания записей.

4. **Документы**: Убедитесь, что документы обработаны (статус `processed`) перед использованием бота.

5. **API Tools**: Настройте реальные URL и токены для внешних API в соответствии с вашей инфраструктурой.

---

## Пример полного сценария использования

1. Пользователь: "Какая цена на смартфон?"
   - Routing → product_info
   - Product_info использует RAG → находит информацию в каталоге
   - Ответ: "Смартфон Galaxy Pro 2024 стоит 45,990 рублей..."

2. Пользователь: "Какие есть свободные окна на завтра?"
   - Routing → available_slots
   - Available_slots вызывает API get_available_slots с параметром date
   - Ответ: "На завтра доступны следующие временные окна: 10:00, 14:00, 16:00..."

3. Пользователь: "Запишите меня на консультацию на завтра в 14:00"
   - Routing → book_appointment
   - Book_appointment собирает данные и вызывает API book_appointment
   - Ответ: "Ваша запись успешно создана! Вы записаны на консультацию на завтра в 14:00..."

4. Пользователь: "Какой у вас адрес?"
   - Routing → general
   - General использует RAG → находит информацию в документах
   - Ответ: "Наш адрес: г. Москва, ул. Торговая, д. 1..."

