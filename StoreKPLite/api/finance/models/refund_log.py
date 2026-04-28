"""
Лог возвратов (рефаундов) по заказам через ЮKassa.
Используется для учёта: вещь возвращена, выполнен рефаунд на сумму X.
"""
from sqlalchemy import Column, Integer, Numeric, Text, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from api.finance.database.database import Base


class RefundLog(Base):
    __tablename__ = "refund_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(Integer, nullable=False, index=True, comment="ID заказа (products)")
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False, index=True, comment="ID платежа в нашей БД")
    amount = Column(Numeric(10, 2), nullable=False, comment="Сумма возврата в рублях")
    reason = Column(Text, nullable=True, comment="Причина возврата (например: вещь возвращена)")
    yookassa_refund_id = Column(String(255), nullable=True, index=True, comment="ID возврата в ЮKassa")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
