"""
Модель доставки заказа
"""
from sqlalchemy import String, Column, Integer, ForeignKey, Text, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class OrderDelivery(Base):
    __tablename__ = "order_deliveries"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True, comment="ID заказа")
    delivery_status_id = Column(Integer, ForeignKey("delivery_statuses.id", ondelete="SET NULL"), nullable=True, index=True, comment="ID статуса доставки")
    additional_info = Column(Text, nullable=True, comment="Дополнительная информация по треку")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Дата обновления")
    
    # Связи
    order = relationship("Order", back_populates="delivery")
    delivery_status = relationship("DeliveryStatus", back_populates="deliveries")

