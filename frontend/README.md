# AI Platform Frontend

React + TypeScript single-page app for the FastAPI backend in `AI-platform`.

## Быстрый старт

1. Установите зависимости:
   ```bash
   cd frontend
   npm install
   ```
2. Запустите дев-сервер:
   ```bash
   npm run dev
   ```
3. По умолчанию запросы идут на `http://localhost:8000/api/v1`. При необходимости задайте:
   ```bash
   VITE_API_URL=http://localhost:8000/api/v1
   ```
   (можно в `.env.local`).

## Возможности

- Регистрация/вход, хранение JWT в `localStorage`
- Переключение workspace и создание новых
- Загрузка/удаление документов
- CRUD API-инструментов
- Создание/обновление/удаление ботов через JSON конфиг графа
- Чат с ботом, выбор сессии или создание новой

## Структура

- `src/api` — запросы к бекенду
- `src/state` — контексты авторизации и workspace
- `src/pages` — основные экраны
- `src/components` — общие компоненты и layout

