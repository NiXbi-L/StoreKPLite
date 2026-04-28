"""
Модель перевода валюты
"""
from sqlalchemy import String, Column, Integer, Numeric, Text, DateTime
from sqlalchemy.sql import func
from api.finance.database.database import Base


class CurrencyTransfer(Base):
    __tablename__ = "currency_transfers"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    amount_from = Column(Numeric(10, 2), nullable=False, comment="Сумма списания (в исходной валюте)")
    currency_from = Column(String(10), nullable=False, comment="Валюта списания: RUB или CNY")
    amount_to = Column(Numeric(10, 2), nullable=False, comment="Сумма получения (в целевой валюте)")
    currency_to = Column(String(10), nullable=False, comment="Валюта получения: RUB или CNY")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания перевода")
    # Используем внутренний ID пользователя (админа) вместо tgid
    created_by_user_id = Column(Integer, nullable=True, comment="Внутренний ID админа из сервиса users")
    notes = Column(Text, nullable=True, comment="Примечания к переводу")

