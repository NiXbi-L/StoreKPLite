"""
Отдельная база данных для Delivery‑сервиса.
"""
from os import getenv
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base


DELIVERY_DATABASE_URL = getenv(
    "DELIVERY_DATABASE_URL",
    getenv("DATABASE_URL", "postgresql+asyncpg://timoshka_user:timoshka_password@postgres:5432/timoshka_delivery"),
)

engine = create_async_engine(DELIVERY_DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def init_db() -> None:
    """
    Инициализация базы данных Delivery‑сервиса.
    """
    from sqlalchemy import text

    # Импорт моделей для регистрации в metadata
    from api.delivery import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Миграция: колонка is_default для основного способа доставки
        await conn.execute(text(
            "ALTER TABLE user_delivery_data ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false"
        ))

