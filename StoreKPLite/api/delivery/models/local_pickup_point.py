"""
Локальные ПВЗ (наши точки выдачи в Уссурийске и т.п.).
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from api.delivery.database.database import Base


class LocalPickupPoint(Base):
    __tablename__ = "local_pickup_points"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    city = Column(String(255), nullable=False, default="Уссурийск", comment="Город ПВЗ")
    address = Column(String(512), nullable=False, comment="Адрес пункта выдачи")
    is_active = Column(Boolean, nullable=False, default=True, comment="Активен ли ПВЗ")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Дата создания",
    )

