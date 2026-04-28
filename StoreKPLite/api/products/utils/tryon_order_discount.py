"""Скидка за AI-примерки отключена в StoreKPLite (сервис примерки и users/finance tryon API удалены)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


def count_order_item_units(order_data: Optional[Dict[str, Any]]) -> int:
    items = (order_data or {}).get("items") or []
    return sum(max(0, int(i.get("quantity") or 0)) for i in items)


async def fetch_finance_tryon_params() -> Tuple[Optional[Decimal], int]:
    return None, 3


async def reserve_tryon_for_order(
    order_id: int,
    user_id: int,
    order_data: dict,
    goods_subtotal: Decimal,
) -> Optional[Dict[str, Any]]:
    return None


async def preview_tryon_discount(
    user_id: int,
    item_units: int,
    goods_subtotal: Decimal,
) -> Dict[str, Any]:
    return {"discount_rub": 0.0, "units_reserved": 0, "bonus_credits_on_complete": 0}


async def release_tryon_for_order(order_id: int, user_id: int) -> None:
    return


async def complete_tryon_for_order(order_id: int, user_id: int) -> None:
    return


def scale_commodity_line_totals(
    line_totals: List[float],
    goods_subtotal: float,
    tryon_discount: float,
) -> List[float]:
    if not line_totals or goods_subtotal <= 0 or tryon_discount <= 0:
        return line_totals
    target = max(0.0, round(goods_subtotal - tryon_discount, 2))
    if target <= 0:
        return [0.0] * len(line_totals)
    raw_sum = sum(line_totals)
    if raw_sum <= 0:
        return line_totals
    factor = target / raw_sum
    scaled = [round(lt * factor, 2) for lt in line_totals]
    drift = round(target - sum(scaled), 2)
    if scaled and abs(drift) >= 0.01:
        scaled[-1] = round(scaled[-1] + drift, 2)
    return scaled
