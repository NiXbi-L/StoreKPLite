# StoreKPLite

Базовый проект интернет-магазина для учебных задач.

В проекте есть:
- клиент (`miniapp_tg`) с каталогом, корзиной и оформлением заказа;
- админка (`admin_react`) для управления каталогом, заказами, администраторами и пользователями;
- backend на FastAPI (`api/*`);
- Telegram-бот и локальный bridge (`bot_tg`, `bot_api_service`);
- reverse-proxy (`nginx`).

## Quick Start

Требования:
- Docker + Docker Compose.

Шаги запуска:

```bash
cd StoreKPLite
cp .env.example .env
docker compose -f docker-compose.kp-local.yml --env-file .env up -d --build
```

После запуска:
- витрина: `http://127.0.0.1/miniapp/`
- админка: `http://127.0.0.1/x9d4k2m7p1/admin/`

Остановка:

```bash
docker compose -f docker-compose.kp-local.yml down
```

## Полезно знать

- Основной локальный сценарий: `docker-compose.kp-local.yml` (HTTP, порт `80`).
- Для переменных окружения используйте `.env.example` как шаблон.

## Лицензия

Проект распространяется по лицензии `StoreKPLite Academic Non-Commercial License v1.0` (см. `LICENSE.md`):
- коммерческое использование запрещено;
- для учебного использования обязательно указание автора;
- производные публичные проекты допускаются только в публичных репозиториях.
