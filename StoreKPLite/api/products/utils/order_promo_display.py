"""Обогащение состава заказа для админки/сборки: позиции со скидкой системного фото-промо."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.models.promocode import PromoRedemption


async def system_photo_promo_lines_by_order(session: AsyncSession, order_ids: List[int]) -> Dict[int, Set[int]]:
    """order_id -> множество item_id, по которым была системная скидка за фото."""
    if not order_ids:
        return {}
    result = await session.execute(
        select(PromoRedemption.order_id, PromoRedemption.item_id).where(
            PromoRedemption.redemption_kind == "system",
            PromoRedemption.order_id.in_(order_ids),
        )
    )
    out: Dict[int, Set[int]] = {}
    for oid, iid in result.all():
        out.setdefault(int(oid), set()).add(int(iid))
    return out


def order_data_with_system_promo_flags(
    order_data: Optional[Dict[str, Any]],
    system_item_ids: Set[int],
) -> Dict[str, Any]:
    """
    Помечает позиции: promo_redemption_kind=system, photo_promo_line=True.
    Нужно для старых заказов, где в JSON не сохранили kind (до изменений) — данные берутся из promo_redemptions.
    """
    if not order_data or not isinstance(order_data, dict):
        return order_data or {}
    items = order_data.get("items")
    if not items:
        return order_data

    new_items: List[Any] = []
    changed = False
    for row in items:
        if not isinstance(row, dict):
            new_items.append(row)
            continue
        d = dict(row)
        iid = d.get("item_id")
        if iid is not None and int(iid) in system_item_ids:
            if d.get("promo_redemption_kind") != "system":
                d["promo_redemption_kind"] = "system"
                changed = True
            if not d.get("photo_promo_line"):
                d["photo_promo_line"] = True
                changed = True
        elif d.get("promo_redemption_kind") == "system" and not d.get("photo_promo_line"):
            d["photo_promo_line"] = True
            changed = True
        new_items.append(d)

    if not changed:
        return order_data
    return {**order_data, "items": new_items}


async def admin_order_data_for_response(
    session: AsyncSession,
    *,
    order_id: int,
    order_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    sm = await system_photo_promo_lines_by_order(session, [order_id])
    return order_data_with_system_promo_flags(order_data, sm.get(order_id, set()))
