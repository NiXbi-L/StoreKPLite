"""
Модель настроек финансов
"""
from sqlalchemy import Column, Integer, Numeric, DateTime, SmallInteger
from sqlalchemy.sql import func
from api.finance.database.database import Base


class FinanceSettings(Base):
    __tablename__ = "finance_settings"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    depreciation_percent = Column(Numeric(5, 2), nullable=False, default=3.00, comment="Процент от прибыли, идущий в амортизационный фонд")
    working_capital_limit = Column(Numeric(10, 2), nullable=True, comment="Лимит оборотного капитала. При превышении излишек переводится в свободный капитал")
    delivery_cost_per_kg = Column(Numeric(10, 2), nullable=True, comment="Стоимость доставки за 1 кг в рублях (глобальная настройка для всех товаров)")
    exchange_rate_margin_percent = Column(Numeric(5, 2), nullable=False, default=10.00, comment="Процент наценки на курс валюты от ЦБ (по умолчанию 10%)")
    yuan_markup_before_rub_percent = Column(
        Numeric(5, 2),
        nullable=False,
        default=0,
        comment="Процент к цене в юанях до перевода в рубли (поверх курса ЦБ+маржа)",
    )
    customer_price_acquiring_factor = Column(
        Numeric(5, 4),
        nullable=False,
        default=0.97,
        comment="Доля выручки после эквайринга (0.97 → цена клиента = сумма/0.97)",
    )
    tryon_unit_price_rub = Column(Numeric(10, 2), nullable=True, comment="Цена одной AI-примерки в рублях (миниапп)")
    tryon_max_discount_units_per_item = Column(
        SmallInteger, nullable=False, default=3, comment="Макс. генераций примерки в зачёт скидки на 1 купленную единицу"
    )
    tryon_generation_internal_cost_rub = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Учётная себестоимость одной примерки (₽), для сравнения с выручкой",
    )
    tryon_clothing_profit_to_api_reserve_percent = Column(
        Numeric(5, 2),
        nullable=True,
        comment="Доля прибыли с одежды, планируемая на пополнение GenAPI (учётная метка, %)",
    )
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="Дата обновления настроек")

