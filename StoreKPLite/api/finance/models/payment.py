"""
Модель платежа через ЮKassa
"""
from sqlalchemy import Column, Integer, String, Numeric, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from api.finance.database.database import Base


class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(Integer, nullable=False, index=True, comment="ID заказа из products-service")
    user_id = Column(Integer, nullable=True, index=True, comment="Внутренний ID пользователя из users-service")
    
    # Данные платежа ЮKassa
    yookassa_payment_id = Column(String(255), nullable=True, unique=True, index=True, comment="ID платежа в ЮKassa")
    amount = Column(Numeric(10, 2), nullable=False, comment="Сумма платежа в рублях")
    currency = Column(String(3), nullable=False, default="RUB", comment="Валюта платежа")
    description = Column(Text, nullable=True, comment="Описание платежа")
    
    # Статус платежа
    status = Column(String(50), nullable=False, default="pending", comment="Статус платежа: pending, succeeded, canceled")
    paid = Column(Boolean, nullable=False, default=False, comment="Платеж оплачен")
    
    # URL для подтверждения
    confirmation_url = Column(Text, nullable=True, comment="URL для редиректа пользователя на оплату")
    return_url = Column(Text, nullable=True, comment="URL возврата после оплаты")
    
    # Метаданные
    payment_metadata = Column(JSON, nullable=True, comment="Дополнительные метаданные платежа")
    
    # Тестовый режим
    test = Column(Boolean, nullable=False, default=False, comment="Тестовый платеж")
    
    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания платежа")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Дата обновления платежа")
    paid_at = Column(DateTime(timezone=True), nullable=True, comment="Дата оплаты платежа")
    
    # Ключ идемпотентности
    idempotence_key = Column(String(255), nullable=True, unique=True, index=True, comment="Ключ идемпотентности для предотвращения дублирования")

    # Чек ЮKassa (54-ФЗ): статус регистрации из GET платежа; id объекта чека из GET /v3/receipts
    receipt_registration = Column(String(64), nullable=True, comment="Статус регистрации чека прихода (из API платежа)")
    yookassa_receipt_id = Column(String(255), nullable=True, index=True, comment="UUID чека в ЮKassa")
    # Снимок позиций, переданных в ЮKassa при создании платежа (для справки/PDF в админке)
    receipt_items_json = Column(JSON, nullable=True, comment="Позиции чека, отправленные в ЮKassa")

    # Публичная ссылка на кассовый документ (Первый ОФД), собранная из фискальных полей чека ЮKassa
    ofd_receipt_url = Column(Text, nullable=True, comment="Ссылка consumer.1-ofd.ru/ticket по данным чека")
    ofd_receipt_telegram_sent = Column(
        Boolean, nullable=False, default=False, comment="Ссылка отправлена пользователю в Telegram"
    )

    @property
    def has_receipt_pdf(self) -> bool:
        return self.receipt_items_json is not None and (
            isinstance(self.receipt_items_json, list) and len(self.receipt_items_json) > 0
        )

