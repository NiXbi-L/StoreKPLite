"""
Модель курса валют
"""
from sqlalchemy import String, Column, Integer, Numeric, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from api.finance.database.database import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    currency_code = Column(String(10), nullable=False, unique=True, comment="Код валюты (CNY для юаня)")
    rate = Column(Numeric(10, 4), nullable=False, comment="Курс валюты к рублю (от ЦБ)")
    rate_with_margin = Column(Numeric(10, 4), nullable=False, comment="Курс с наценкой 10%")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Дата последнего обновления курса")

