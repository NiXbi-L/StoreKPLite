"""
Модель финансовой поставки
"""
from sqlalchemy import Column, Integer, Numeric, JSON, Text, DateTime, Boolean
from sqlalchemy.sql import func
from api.finance.database.database import Base


class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_ids = Column(JSON, nullable=False, comment="Список ID заказов в формате JSON")
    purchase_cost = Column(Numeric(10, 2), nullable=False, comment="Фактическая стоимость выкупа товаров для этих заказов (в рублях)")
    delivery_cost = Column(Numeric(10, 2), nullable=False, comment="Фактическая стоимость доставки (в рублях)")
    weight_kg = Column(Numeric(10, 3), nullable=True, comment="Вес поставки в килограммах")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания поставки")
    # Используем внутренний ID пользователя (админа) вместо tgid
    created_by_user_id = Column(Integer, nullable=True, comment="Внутренний ID админа из сервиса users")
    notes = Column(Text, nullable=True, comment="Примечания к поставке")
    is_archived = Column(Boolean, default=False, nullable=False, comment="Флаг архивации поставки")

