"""
Модель транзакции счета
"""
from sqlalchemy import String, Column, Integer, Numeric, Text, DateTime
from sqlalchemy.sql import func
from api.finance.database.database import Base


class AccountTransaction(Base):
    __tablename__ = "account_transactions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    transaction_type = Column(
        String(50),
        nullable=False,
        comment="Тип операции: deposit (пополнение), withdrawal (снятие), transfer (перевод)"
    )
    account_from = Column(
        String(50),
        nullable=True,
        comment="Счет-источник (для переводов и снятий): depreciation_fund, working_capital, free_capital"
    )
    account_to = Column(
        String(50),
        nullable=True,
        comment="Счет-получатель (для переводов и пополнений): depreciation_fund, working_capital, free_capital"
    )
    amount = Column(Numeric(10, 2), nullable=False, comment="Сумма операции")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания операции")
    # Используем внутренний ID пользователя (админа) вместо tgid
    created_by_user_id = Column(Integer, nullable=True, comment="Внутренний ID админа из сервиса users")
    notes = Column(Text, nullable=True, comment="Примечания к операции")

