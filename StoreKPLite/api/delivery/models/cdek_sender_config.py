"""
Настройка города/ПВЗ СДЭК, откуда ведётся отправка (по умолчанию Уссурийск).
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from api.delivery.database.database import Base


class CdekSenderConfig(Base):
    __tablename__ = "cdek_sender_config"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    city_name = Column(
        String(255),
        nullable=False,
        default="Уссурийск",
        comment="Название города отправителя для расчёта СДЭК (по умолчанию Уссурийск)",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
