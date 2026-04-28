"""
Модель группы товаров
"""
from sqlalchemy import String, Column, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class ItemGroup(Base):
    __tablename__ = "item_groups"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, comment="Название группы")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания")
    
    # Связи
    items = relationship("Item", back_populates="group", cascade="all, delete-orphan")



