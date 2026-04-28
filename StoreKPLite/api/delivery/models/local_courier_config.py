"""
Настройки локальной курьерской доставки по городу (единая цена).
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.sql import func

from api.delivery.database.database import Base


class LocalCourierConfig(Base):
    __tablename__ = "local_courier_config"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    city = Column(String(255), nullable=False, default="Уссурийск", comment="Город курьерской доставки")
    price_rub = Column(Numeric(10, 2), nullable=True, comment="Стоимость курьерской доставки по городу, ₽")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Дата создания",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Дата последнего обновления",
    )

