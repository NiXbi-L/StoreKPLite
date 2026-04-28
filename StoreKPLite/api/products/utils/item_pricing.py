"""
Упрощённый расчёт цены товара для StoreKPLite: только фиксированная цена в рублях.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from api.products.models.item import Item
from api.products.utils.finance_context import FinancePriceContext

_DEFAULT_ACQUIRING_FACTOR = Decimal("1")


def _item_fixed_price_rub(item: Item) -> Decimal:
    """Единая цена товара в ₽: fixed_price приоритетно, иначе legacy поле price."""
    if getattr(item, "fixed_price", None) is not None:
        return Decimal(str(item.fixed_price)).quantize(Decimal("0.01"))
    return Decimal(str(item.price)).quantize(Decimal("0.01"))


def item_price_rub_base_after_yuan_markup(
    item: Item,
    exchange_rate: Decimal,
    yuan_markup_before_rub_percent: Decimal = Decimal("0"),
) -> Decimal:
    _ = exchange_rate
    _ = yuan_markup_before_rub_percent
    return _item_fixed_price_rub(item)


def item_sebestoimost_rub(
    item: Item,
    exchange_rate: Decimal,
    delivery_cost_per_kg: Optional[Decimal],
    yuan_markup_before_rub_percent: Decimal = Decimal("0"),
) -> Decimal:
    _ = exchange_rate
    _ = delivery_cost_per_kg
    _ = yuan_markup_before_rub_percent
    return _item_fixed_price_rub(item)


def is_owner_checkout_price_context(ctx: FinancePriceContext) -> bool:
    _ = ctx
    return False


def compute_item_owner_landed_unit_rub(
    item: Item,
    exchange_rate: Decimal,
    delivery_cost_per_kg: Optional[Decimal],
) -> Decimal:
    _ = exchange_rate
    _ = delivery_cost_per_kg
    return _item_fixed_price_rub(item)


def compute_item_unit_price_for_ctx(item: Item, ctx: FinancePriceContext) -> Decimal:
    """Одна точка входа: витринная цена клиента или удельная закупка владельца — по контексту owner-checkout."""
    if is_owner_checkout_price_context(ctx):
        return compute_item_owner_landed_unit_rub(item, ctx.rate_with_margin, ctx.delivery_cost_per_kg)
    return compute_item_customer_price_rub(
        item,
        ctx.rate_with_margin,
        ctx.delivery_cost_per_kg,
        yuan_markup_before_rub_percent=ctx.yuan_markup_before_rub_percent,
        customer_price_acquiring_factor=ctx.customer_price_acquiring_factor,
    )


def compute_item_customer_price_rub(
    item: Item,
    exchange_rate: Decimal,
    delivery_cost_per_kg: Optional[Decimal],
    *,
    yuan_markup_before_rub_percent: Decimal = Decimal("0"),
    customer_price_acquiring_factor: Decimal = _DEFAULT_ACQUIRING_FACTOR,
) -> Decimal:
    _ = exchange_rate
    _ = delivery_cost_per_kg
    _ = yuan_markup_before_rub_percent
    _ = customer_price_acquiring_factor
    return _item_fixed_price_rub(item)
