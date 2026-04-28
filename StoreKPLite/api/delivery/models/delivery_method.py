"""
Модель способа доставки (Delivery‑сервис).
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from api.delivery.database.database import Base


class DeliveryMethod(Base):
    __tablename__ = "delivery_methods"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, comment="Название способа доставки")
    requires_address = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Требуется адрес (True - адрес проживания, False - адрес ПВЗ)",
    )
    address_not_required = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Адрес не требуется (True - пропустить ввод адреса, поставить прочерк)",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Дата создания",
    )

    # Связи
    user_delivery_data = relationship("UserDeliveryData", back_populates="delivery_method")

