"""
Резерв «потраченных примерок» под скидку по заказу (до завершения заказа баланс не меняется).
"""
from sqlalchemy import Column, Integer, DateTime, Numeric
from sqlalchemy.sql import func

from api.users.database.database import Base


class TryonOrderDiscountReservation(Base):
    __tablename__ = "tryon_order_discount_reservations"

    order_id = Column(Integer, primary_key=True, comment="orders.id в products-service")
    user_id = Column(Integer, nullable=False, index=True)
    units_reserved = Column(Integer, nullable=False, comment="Сколько генераций примерок уйдёт в зачёт скидки при завершении")
    bonus_credits_on_complete = Column(
        Integer, nullable=False, default=0, comment="Начислить tryon_credits при завершении заказа"
    )
    discount_rub = Column(Numeric(10, 2), nullable=False, default=0, comment="Скидка в ₽ на момент оформления")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
