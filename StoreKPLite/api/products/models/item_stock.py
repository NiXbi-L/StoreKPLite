"""
Модель остатков на складе по товару и размеру
"""
from sqlalchemy import String, Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class ItemStock(Base):
    __tablename__ = "item_stock"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    size = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)

    item = relationship("Item", back_populates="stock")
