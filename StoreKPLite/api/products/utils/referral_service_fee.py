"""База для реферальной комиссии: «сервисный сбор» (наценка) по строкам заказа, как в админке."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.models.item import Item
from api.products.utils.item_pricing import item_price_rub_base_after_yuan_markup


def line_service_fee_rub_for_item(
    item: Item,
    exchange_rate: Decimal,
    quantity: int = 1,
    yuan_markup_before_rub_percent: Decimal = Decimal("0"),
) -> Decimal:
    """Наценка в ₽ за qty шт. (как «Ориентировочный доход с продажи» в карточке товара)."""
    qty = max(1, int(quantity or 1))
    price_rub_base = item_price_rub_base_after_yuan_markup(item, exchange_rate, yuan_markup_before_rub_percent)
    pct = Decimal(str(item.service_fee_percent or 0))
    per_unit = price_rub_base * (pct / Decimal("100"))
    return (per_unit * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def sum_order_lines_service_fee_base_rub(
    session: AsyncSession,
    order_items: List[Dict[str, Any]],
    exchange_rate: Decimal,
    yuan_markup_before_rub_percent: Decimal = Decimal("0"),
) -> Decimal:
    """Сумма сервисного сбора по всем не возвращённым позициям заказа."""
    item_ids: List[int] = []
    for row in order_items:
        if row.get("returned"):
            continue
        iid = row.get("item_id")
        if iid is not None:
            item_ids.append(int(iid))
    if not item_ids:
        return Decimal("0")
    res = await session.execute(select(Item).where(Item.id.in_(item_ids)))
    items = {it.id: it for it in res.scalars().all()}
    total = Decimal("0")
    for row in order_items:
        if row.get("returned"):
            continue
        iid = row.get("item_id")
        if iid is None:
            continue
        it = items.get(int(iid))
        if not it:
            continue
        qty = max(1, int(row.get("quantity") or 1))
        total += line_service_fee_rub_for_item(
            it,
            exchange_rate,
            qty,
            yuan_markup_before_rub_percent=yuan_markup_before_rub_percent,
        )
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
