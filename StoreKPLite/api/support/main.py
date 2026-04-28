"""
FastAPI приложение для микросервиса поддержки
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.shared.cors import cors_allowed_origins
from api.support.database.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "false").lower() in {"1", "true", "yes"}

app = FastAPI(
    title="Support Service",
    description="Микросервис поддержки MatchWear",
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
        logger.info("База данных сервиса поддержки инициализирована")
    except Exception:
        logger.exception("Ошибка при инициализации БД support-service; прерываем старт")
        raise


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "support"}


# Подключаем роутеры
from api.support.routers import faq, tickets, cascade_delete

app.include_router(faq.router, tags=["faq"])
app.include_router(tickets.router, tags=["tickets"])
app.include_router(cascade_delete.router, tags=["internal"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)

