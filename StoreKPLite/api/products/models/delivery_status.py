"""
Модель статуса доставки
"""
from sqlalchemy import String, Column, Integer, Text, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class DeliveryStatus(Base):
    __tablename__ = "delivery_statuses"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, comment="Название статуса доставки")
    description = Column(Text, nullable=True, comment="Описание статуса")
    require_payment = Column(Boolean, nullable=False, default=False, comment="Требовать оплату остатка при установке этого статуса")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания")
    
    # Связи
    deliveries = relationship("OrderDelivery", back_populates="delivery_status")

