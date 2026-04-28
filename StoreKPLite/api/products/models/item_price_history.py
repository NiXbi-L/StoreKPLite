"""
Модель истории цен товара.
Храним срезы по 4 часа (bucket): week_start = начало 4h-окна (00:00, 04:00, 08:00, 12:00, 16:00, 20:00) по Владивостоку.
Для отображения: за прошедшие дни — одна точка в день (средняя за день); за текущий день — точки по 4 часа.
"""
from sqlalchemy import Column, Integer, ForeignKey, Numeric, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class ItemPriceHistory(Base):
    __tablename__ = "item_price_history"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True, comment="ID товара")
    week_start = Column(DateTime(timezone=True), nullable=False, index=True, comment="Начало 4h-окна (00/04/08/12/16/20) или день для агрегации")
    min_price = Column(Numeric(10, 2), nullable=False, comment="Минимальная цена за период в рублях")
    max_price = Column(Numeric(10, 2), nullable=False, comment="Максимальная цена за период в рублях")
    avg_price = Column(Numeric(10, 2), nullable=True, comment="Средняя цена за период (для графика)")
    sample_count = Column(Integer, nullable=False, default=1, comment="Кол-во сэмплов для расчёта средней")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания записи")
    
    # Связь с товаром
    item = relationship("Item", back_populates="price_history")

