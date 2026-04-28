"""
Модель баланса счета
"""
from sqlalchemy import String, Column, Integer, Numeric, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from api.finance.database.database import Base


class AccountBalance(Base):
    __tablename__ = "account_balances"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    account_type = Column(
        String(50),
        nullable=False,
        unique=True,
        comment="Тип счета: depreciation_fund, working_capital, free_capital"
    )
    balance = Column(Numeric(10, 2), nullable=False, default=0, comment="Текущий баланс счета")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Дата обновления баланса")

