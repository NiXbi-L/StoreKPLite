"""
Модель корзины
"""
from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class Cart(Base):
    __tablename__ = "cart"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # Используем внутренний ID пользователя вместо tgid
    user_id = Column(Integer, nullable=False, index=True, comment="Внутренний ID пользователя из сервиса users")
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True, comment="ID вещи")
    size = Column(String(50), nullable=True, comment="Выбранный размер товара")
    quantity = Column(Integer, nullable=False, default=1, comment="Количество единиц")
    stock_type = Column(String(20), nullable=False, default="preorder", comment="Тип заказа: preorder (предзаказ) или in_stock (из наличия)")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата добавления")
    
    # Уникальный индекс на комбинацию user_id + item_id + size + stock_type (одинаковый товар с разным размером и типом - разные позиции)
    __table_args__ = (
        UniqueConstraint('user_id', 'item_id', 'size', 'stock_type', name='uq_cart_user_item_size_stock'),
    )
    
    # Связи
    item = relationship("Item", back_populates="cart_items")

