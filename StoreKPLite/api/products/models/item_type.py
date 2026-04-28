"""
Модель типа вещи
"""
from sqlalchemy import String, Column, Integer, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class ItemType(Base):
    __tablename__ = "item_types"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True, comment="Название типа вещи")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Дата создания")
    items_count = Column(Integer, nullable=False, default=0, server_default="0", comment="Количество товаров этого типа в каталоге (денормализация для фильтра)")
    
    # Связи
    items = relationship("Item", back_populates="item_type_rel")
