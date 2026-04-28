"""Промокоды и системный «фото»-промо (уникальная скидка 1 раз на товар в рамках акции)."""
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Numeric,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from api.products.database.database import Base


class Promocode(Base):
    __tablename__ = "promocodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code_normalized = Column(String(64), unique=True, nullable=False, index=True)
    discount_percent = Column(Numeric(5, 2), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scope_all = Column(Boolean, nullable=False, default=True)
    # False: item_ids — белый список; True: item_ids — чёрный список (скидка на все, кроме перечисленных)
    pool_is_blacklist = Column(Boolean, nullable=False, default=False)
    # multi — многоразовый (срок expires_at, опц. max_uses_total на всех, опц. max_uses_per_user);
    # once_per_user — 1 заказ на пользователя (каждый может 1 раз);
    # устаревшие в БД: once_total (≈ multi + max_uses_total), unique_per_item (1 списание на товар — только наследие)
    usage_kind = Column(String(24), nullable=False, default="multi")
    max_uses_total = Column(Integer, nullable=True)
    max_uses_per_user = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Реферальный промокод: процент от «сервисного сбора» (наценки) по заказу — см. referral_snapshot в order_data
    referrer_user_id = Column(Integer, nullable=True, index=True, comment="Внутренний users.id владельца промокода")
    referral_commission_percent = Column(
        Numeric(5, 2),
        nullable=True,
        comment="Процент от суммы сервисного сбора по заказу, начисляемый владельцу",
    )

    items = relationship("PromocodeItem", back_populates="promocode", cascade="all, delete-orphan")


class PromocodeItem(Base):
    __tablename__ = "promocode_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    promocode_id = Column(Integer, ForeignKey("promocodes.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)

    promocode = relationship("Promocode", back_populates="items")

    __table_args__ = (UniqueConstraint("promocode_id", "item_id", name="uq_promocode_item"),)


class SystemPhotoPromoSettings(Base):
    """Одна строка id=1: включаемый промо для съёмки каталога, код и % меняются, история по item_id хранится отдельно."""

    __tablename__ = "system_photo_promo_settings"

    id = Column(Integer, primary_key=True)
    is_enabled = Column(Boolean, nullable=False, default=False)
    discount_percent = Column(Numeric(5, 2), nullable=False, default=10)
    current_code_normalized = Column(String(64), nullable=False, default="")
    badge_label = Column(String(128), nullable=True)
    # False: перечисленные item_id — белый список; True — чёрный список (пустая таблица = весь каталог)
    pool_is_blacklist = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SystemPhotoPromoItem(Base):
    """Пустая таблица = действует на все товары; иначе только перечисленные."""

    __tablename__ = "system_photo_promo_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)


class PromoRedemption(Base):
    """Факт применения скидки по строке заказа (метрики + уникальность по товару)."""

    __tablename__ = "promo_redemptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    redemption_kind = Column(String(16), nullable=False, index=True)  # system | admin
    admin_promocode_id = Column(Integer, ForeignKey("promocodes.id", ondelete="SET NULL"), nullable=True, index=True)
    item_id = Column(Integer, nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    discount_rub = Column(Numeric(10, 2), nullable=False)
    code_entered_snapshot = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
