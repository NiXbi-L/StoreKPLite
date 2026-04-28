"""
Модель данных доставки пользователя (Delivery‑сервис).
"""
from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from api.delivery.database.database import Base


class UserDeliveryData(Base):
    __tablename__ = "user_delivery_data"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="Внутренний ID пользователя из сервиса users")
    phone_number = Column(String(20), nullable=True, comment="Номер телефона пользователя")
    recipient_name = Column(
        String(255),
        nullable=True,
        comment="ФИО получателя (если отличается от профиля пользователя)",
    )
    delivery_method_id = Column(
        Integer,
        ForeignKey("delivery_methods.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ID способа доставки",
    )
    address = Column(
        Text,
        nullable=True,
        comment="Адрес доставки: для CDEK — полный адрес ПВЗ без страны (край, город, улица, ...) для накладной",
    )
    postal_code = Column(String(32), nullable=True, comment="Индекс (для СДЭК и др.)")
    city_code = Column(Integer, nullable=True, comment="Код города в системе СДЭК")
    cdek_delivery_point_code = Column(
        String(64),
        nullable=True,
        comment="Код ПВЗ/офиса СДЭК (поле delivery_point при создании заказа в API СДЭК)",
    )
    is_default = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Основной способ доставки для пользователя (только один на пользователя)",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Дата создания",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Дата обновления",
    )

    # Связи
    delivery_method = relationship("DeliveryMethod", back_populates="user_delivery_data")

