"""
Модель заказа
"""
from sqlalchemy import String, Column, Integer, Numeric, Text, JSON, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from api.products.database.database import Base


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True, comment="Внутренний ID пользователя из сервиса users")
    recipient_name = Column(String(255), nullable=True, comment="ФИО получателя для доставки/накладной")
    order_data = Column(JSON, nullable=False, comment="Состав заказа в формате JSON (items[] с item_id в строке)")
    status = Column(
        String(20),
        nullable=False,
        default="Ожидает",
        comment="Статус заказа: Ожидает, Выкуп, в работе, Собран, отменен, завершен"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Дата создания заказа")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Дата обновления заказа")
    cancel_reason = Column(Text, nullable=True, comment="Причина отмены заказа (со стороны магазина)")
    paid_amount = Column(Numeric(10, 2), nullable=False, default=0, comment="Внесенные средства клиентом по данному заказу")
    refund_on_cancel = Column(Boolean, nullable=True, comment="Возврат средств при отмене заказа: True - с возвратом, False - без возврата")
    phone_number = Column(String(20), nullable=True, comment="Номер телефона для доставки")
    is_from_stock = Column(Boolean, nullable=False, default=False, index=True, comment="Заказ со склада (True) или предзаказ (False)")
    tracking_number = Column(String(255), nullable=True, index=True, comment="Трек-номер накладной (СДЭК), заполняется при создании накладной")
    hidden_from_user_at = Column(DateTime(timezone=True), nullable=True, comment="Когда пользователь скрыл заказ из списка (мягкое удаление)")
    tryon_discount_rub = Column(
        Numeric(10, 2), nullable=False, default=0, comment="Скидка за AI-примерки (₽), зарезервировано при оформлении"
    )
    tryon_discount_units_reserved = Column(
        Integer, nullable=False, default=0, comment="Генераций в зачёт скидки (списывается с пула при завершении заказа)"
    )
    tryon_discount_bonus_credits = Column(
        Integer, nullable=False, default=0, comment="Бонусные примерки к начислению при завершении (копия из users-резерва)"
    )
    tryon_discount_settled = Column(
        Boolean, nullable=False, default=False, comment="True после успешного complete в users (applied + бонусы)"
    )

    # Связь с доставкой
    delivery = relationship("OrderDelivery", back_populates="order", uselist=False, cascade="all, delete-orphan")

