"""
FastAPI приложение для микросервиса доставки
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.shared.cors import cors_allowed_origins
from api.delivery.database.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").lower() in {"1", "true", "yes"}

app = FastAPI(
    title="Delivery Service",
    description="Микросервис доставки MatchWear (пока использует БД товаров)",
    version="1.0.0",
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """
    Инициализация при запуске.

    Пока просто инициализируем БД через модуль продуктов.
    """
    try:
        await init_db()
        logger.info("База данных сервиса доставки инициализирована (через products DB)")
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка при инициализации БД delivery-service; прерываем старт")
        raise


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "ok", "service": "delivery"}


# Роутеры Delivery (импорт напрямую из модулей, чтобы избежать циклического импорта в routers/__init__.py)
from api.delivery.routers.pickup_points import router as pickup_points_router
from api.delivery.routers.user_delivery_data import router as user_delivery_data_router
from api.delivery.routers.methods import router as methods_router
from api.delivery.routers.internal_user_delete import router as internal_user_delete_router
from api.delivery.routers.internal_checkout_preset import router as internal_checkout_preset_router
from api.delivery.routers.delivery_local_admin import router as delivery_local_admin_router

app.include_router(pickup_points_router, tags=["pickup-points"])
app.include_router(user_delivery_data_router, tags=["user-delivery-data"])
app.include_router(methods_router, tags=["delivery-methods"])
app.include_router(delivery_local_admin_router, tags=["delivery-local-admin"])

app.include_router(internal_user_delete_router, tags=["internal"])
app.include_router(internal_checkout_preset_router, tags=["internal"])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)

