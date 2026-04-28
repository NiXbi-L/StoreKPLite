"""
Модель резервирования товара (размер, количество, пользователь, статус).
Привязка к заказу (order_id): при отмене заказа — снять резерв (cancelled);
при завершении/сборке — перевести в списание (used) и уменьшить ItemStock.
"""
from sqlalchemy import String, Column, Integer, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class ItemReservation(Base):
    __tablename__ = "item_reservations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    size = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(20), nullable=False, default="active", index=True)  # active, cancelled, used

    item = relationship("Item", back_populates="reservations")
