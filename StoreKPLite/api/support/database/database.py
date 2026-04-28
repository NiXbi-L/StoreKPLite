"""
Настройка базы данных для сервиса поддержки
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from os import getenv

DATABASE_URL = getenv(
    "SUPPORT_DATABASE_URL",
    getenv("DATABASE_URL", "postgresql+asyncpg://timoshka_user:timoshka_password@postgres:5432/timoshka_support")
)

engine = create_async_engine(DATABASE_URL, echo=True)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


from typing import AsyncGenerator

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def init_db():
    """Инициализация базы данных"""
    from api.support.models import FAQ, SupportTicket  # noqa: F401
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

