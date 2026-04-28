"""
Модель продажи
"""
from sqlalchemy import Column, Integer, Numeric, Text, DateTime
from sqlalchemy.sql import func
from api.finance.database.database import Base


class Sale(Base):
    __tablename__ = "sales"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(Integer, nullable=True, comment="ID заказа из сервиса products, по которому была продажа (может быть отмененным)")
    profit_amount = Column(Numeric(10, 2), nullable=False, comment="Сумма прибыли от продажи")
    frozen_funds_paid = Column(Numeric(10, 2), nullable=False, default=0, comment="Сумма, пошедшая на погашение замороженных средств")
    working_capital_added = Column(Numeric(10, 2), nullable=False, default=0, comment="Сумма, пошедшая в оборотный счет")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания продажи")
    # Используем внутренний ID пользователя (админа) вместо tgid
    created_by_user_id = Column(Integer, nullable=True, comment="Внутренний ID админа из сервиса users")
    notes = Column(Text, nullable=True, comment="Примечания к продаже")

