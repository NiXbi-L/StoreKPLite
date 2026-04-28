"""
Платежи за AI-примерки (отдельно от заказов / payments).
Без холдирования: capture сразу при создании в ЮKassa.
"""
from sqlalchemy import Column, Integer, String, Numeric, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from api.finance.database.database import Base


class TryonPayment(Base):
    __tablename__ = "tryon_payments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="users.id")
    quantity = Column(Integer, nullable=False, comment="Сколько примерок куплено")

    yookassa_payment_id = Column(String(255), nullable=True, unique=True, index=True)
    amount = Column(Numeric(10, 2), nullable=False, comment="Сумма в рублях")
    currency = Column(String(3), nullable=False, default="RUB")
    description = Column(Text, nullable=True)

    status = Column(String(50), nullable=False, default="pending")
    paid = Column(Boolean, nullable=False, default=False)

    confirmation_url = Column(Text, nullable=True)
    return_url = Column(Text, nullable=True)
    payment_metadata = Column(JSON, nullable=True)
    test = Column(Boolean, nullable=False, default=False)

    idempotence_key = Column(String(255), nullable=True, unique=True, index=True)

    credits_granted = Column(Boolean, nullable=False, default=False, comment="Кредиты начислены в users после succeeded")

    ofd_receipt_url = Column(Text, nullable=True, comment="Ссылка consumer.1-ofd.ru/ticket по чеку ЮKassa")
    ofd_receipt_telegram_sent = Column(
        Boolean, nullable=False, default=False, comment="Ссылка ОФД отправлена в Telegram"
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
