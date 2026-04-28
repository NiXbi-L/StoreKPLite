"""
FastAPI приложение для микросервиса финансов
"""
import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.shared.cors import cors_allowed_origins
from api.finance.database.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").lower() in {"1", "true", "yes"}

app = FastAPI(
    title="Finance Service",
    description="Микросервис финансов MatchWear",
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
    try:
        await init_db()
        logger.info("База данных сервиса финансов инициализирована")
        
        # Загружаем курс валют при запуске
        from api.finance.utils.exchange_rate_loader import load_exchange_rate
        try:
            success = await load_exchange_rate()
            if success:
                logger.info("Курс валют загружен при запуске")
            else:
                logger.warning("Не удалось загрузить курс валют при запуске (проверьте доступность API ЦБ)")
        except Exception as e:
            logger.error(f"Ошибка при загрузке курса валют при запуске: {e}", exc_info=True)

        # Фоновая задача: обновление курса раз в час
        async def update_exchange_rate_periodically():
            while True:
                await asyncio.sleep(3600)  # 1 час
                try:
                    success = await load_exchange_rate()
                    if success:
                        logger.info("Курс валют обновлён по расписанию (раз в час)")
                    else:
                        logger.warning("Не удалось обновить курс по расписанию")
                except Exception as e:
                    logger.error(f"Ошибка при обновлении курса по расписанию: {e}", exc_info=True)

        asyncio.create_task(update_exchange_rate_periodically())
        logger.info("Запущено периодическое обновление курса валют (каждый час)")

    except Exception:
        logger.exception("Ошибка при инициализации БД finance-service; прерываем старт")
        raise


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "finance",
    }


# Подключаем роутеры
from api.finance.routers import settings, orders, payments

app.include_router(settings.router, tags=["settings"])
app.include_router(orders.router, tags=["internal"])
app.include_router(payments.router, tags=["payments"])

from api.finance.routers import cascade_delete
app.include_router(cascade_delete.router, tags=["internal"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)

