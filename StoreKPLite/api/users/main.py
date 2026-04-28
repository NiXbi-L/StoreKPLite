"""
FastAPI приложение для микросервиса пользователей
"""
import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.shared.cors import cors_allowed_origins
from api.users.database.database import (
    init_db,
    migrate_legacy_admin_roles_to_staff,
    ensure_admin_roles_seeded,
    backfill_staff_role_id_from_legacy_json,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").lower() in {"1", "true", "yes"}

app = FastAPI(
    title="Users Service",
    description="Микросервис пользователей MatchWear",
    version="1.0.0",
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)

# CORS: CORS_ALLOWED_ORIGINS через запятую; по умолчанию прод-миниапп
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    try:
        await init_db()
        await ensure_admin_roles_seeded()
        await migrate_legacy_admin_roles_to_staff()
        await backfill_staff_role_id_from_legacy_json()
        logger.info("База данных сервиса пользователей инициализирована")
    except Exception:
        # Не продолжаем запуск в полу-рабочем состоянии без схемы БД.
        logger.exception("Ошибка при инициализации БД users-service; прерываем старт")
        raise

    from api.users.services.traffic_background import nginx_access_log_ingest_loop, online_snapshot_loop

    asyncio.create_task(online_snapshot_loop())
    asyncio.create_task(nginx_access_log_ingest_loop())
    logger.info("Запущены фоновые задачи: online_snapshots, nginx_log_ingest")


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "ok", "service": "users"}


# Подключаем роутеры
from api.users.routers import auth, users, admin, presence
from api.users.routers import public_runtime, admin_runtime, browser_login

app.include_router(auth.router, tags=["auth"])
app.include_router(browser_login.router, tags=["auth"])
app.include_router(users.router, tags=["users"])
app.include_router(presence.router, tags=["users"])
app.include_router(admin.router, tags=["admin"])
app.include_router(public_runtime.router, tags=["public"])
app.include_router(admin_runtime.router, tags=["admin_system"])

from api.users.routers import phone_internal
from api.users.routers import internal_user_lookup
app.include_router(phone_internal.router, tags=["internal"])
app.include_router(internal_user_lookup.router, tags=["internal"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

