"""Применение промокодов к позициям чекаута (админские + системный фото-промо)."""
from __future__ import annotations

import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.models.item import Item
from api.products.models.promocode import (
    Promocode,
    PromocodeItem,
    PromoRedemption,
    SystemPhotoPromoItem,
    SystemPhotoPromoSettings,
)
from api.products.utils.item_pricing import item_sebestoimost_rub

logger = logging.getLogger(__name__)

_STORE_KP_LITE = os.getenv("STORE_KP_LITE", "").lower() in {"1", "true", "yes"}

MAX_PROMO_DISCOUNT_PERCENT = Decimal("70")


def normalize_promo_code(code: Optional[str]) -> str:
    return (code or "").strip().upper()


def _effective_percent(raw: Decimal) -> Decimal:
    p = Decimal(str(raw))
    if p < 0:
        p = Decimal(0)
    return min(p, MAX_PROMO_DISCOUNT_PERCENT)


async def _system_pool_item_ids(session: AsyncSession) -> Optional[set]:
    """None = все товары; иначе множество id."""
    r = await session.execute(select(SystemPhotoPromoItem.item_id))
    ids = {row[0] for row in r.all()}
    if not ids:
        return None
    return ids


async def item_eligible_for_system_photo_promo(session: AsyncSession, item_id: int) -> bool:
    pool = await _system_pool_item_ids(session)
    st = await session.get(SystemPhotoPromoSettings, 1)
    bl = bool(getattr(st, "pool_is_blacklist", False)) if st else False
    if pool is None:
        return True
    if bl:
        return item_id not in pool
    return item_id in pool


async def batch_system_photo_promo_badges(
    session: AsyncSession,
    item_ids: List[int],
) -> Dict[int, Optional[str]]:
    uniq = list({int(i) for i in item_ids if i is not None})
    if not uniq:
        return {}
    st = await session.get(SystemPhotoPromoSettings, 1)
    if not st or not st.is_enabled or not (st.current_code_normalized or "").strip():
        return {i: None for i in uniq}
    pool = await _system_pool_item_ids(session)
    bl = bool(getattr(st, "pool_is_blacklist", False))
    r = await session.execute(
        select(PromoRedemption.item_id)
        .where(
            PromoRedemption.redemption_kind == "system",
            PromoRedemption.item_id.in_(uniq),
        )
        .distinct()
    )
    redeemed = {row[0] for row in r.all()}
    label = (st.badge_label or "").strip() or "Скидка за фото"
    out: Dict[int, Optional[str]] = {}

    def system_pool_match(iid: int) -> bool:
        if pool is None:
            return True
        if bl:
            return iid not in pool
        return iid in pool

    for iid in uniq:
        if not system_pool_match(iid):
            out[iid] = None
        elif iid in redeemed:
            out[iid] = None
        else:
            out[iid] = label
    return out


async def system_photo_promo_badge_for_item(session: AsyncSession, item_id: int) -> Optional[str]:
    m = await batch_system_photo_promo_badges(session, [item_id])
    return m.get(item_id)


async def _line_already_used_system(item_id: int, session: AsyncSession) -> bool:
    r = await session.execute(
        select(func.count())
        .select_from(PromoRedemption)
        .where(
            PromoRedemption.redemption_kind == "system",
            PromoRedemption.item_id == item_id,
        )
    )
    return (r.scalar() or 0) > 0


async def _line_already_used_admin_unique(promo_id: int, item_id: int, session: AsyncSession) -> bool:
    r = await session.execute(
        select(func.count())
        .select_from(PromoRedemption)
        .where(
            PromoRedemption.redemption_kind == "admin",
            PromoRedemption.admin_promocode_id == promo_id,
            PromoRedemption.item_id == item_id,
        )
    )
    return (r.scalar() or 0) > 0


async def _admin_promo_total_orders(promo_id: int, session: AsyncSession) -> int:
    r = await session.execute(
        select(func.count(func.distinct(PromoRedemption.order_id)))
        .select_from(PromoRedemption)
        .where(
            PromoRedemption.redemption_kind == "admin",
            PromoRedemption.admin_promocode_id == promo_id,
        )
    )
    return int(r.scalar() or 0)


async def _admin_promo_user_orders(promo_id: int, user_id: int, session: AsyncSession) -> int:
    r = await session.execute(
        select(func.count(func.distinct(PromoRedemption.order_id)))
        .select_from(PromoRedemption)
        .where(
            PromoRedemption.redemption_kind == "admin",
            PromoRedemption.admin_promocode_id == promo_id,
            PromoRedemption.user_id == user_id,
        )
    )
    return int(r.scalar() or 0)


async def delete_promo_redemptions_for_order(session: AsyncSession, order_id: int) -> int:
    """Удаляет факты применения промо по заказу (при отмене заказа — лимиты снова доступны)."""
    r = await session.execute(delete(PromoRedemption).where(PromoRedemption.order_id == order_id))
    return int(r.rowcount or 0)


def record_promo_redemptions_for_order(
    session: AsyncSession,
    order_id: int,
    user_id: int,
    lines: List[Dict[str, Any]],
    code_snapshot: str,
) -> None:
    snap = (code_snapshot or "")[:64]
    for row in lines:
        d = row.get("promo_discount_rub")
        if not d or float(d) <= 0:
            continue
        session.add(
            PromoRedemption(
                redemption_kind=row.get("promo_redemption_kind") or "admin",
                admin_promocode_id=row.get("promo_admin_id"),
                item_id=int(row["item_id"]),
                order_id=order_id,
                user_id=user_id,
                discount_rub=Decimal(str(d)),
                code_entered_snapshot=snap or None,
            )
        )


async def apply_promo_to_checkout_lines(
    session: AsyncSession,
    user_id: int,
    promo_code: Optional[str],
    lines: List[Dict[str, Any]],
    *,
    code_snapshot: str,
    lock_promo_row: bool = False,
    exchange_rate: Optional[Decimal] = None,
    delivery_cost_per_kg: Optional[Decimal] = None,
    yuan_markup_before_rub_percent: Optional[Decimal] = None,
) -> Tuple[List[Dict[str, Any]], Decimal, Optional[str]]:
    """
    Возвращает (новые линии с изменённым price и метаданными, сумма скидки по промо, ошибка).
    Если ошибка — lines не меняем и возвращаем оригинал? Лучше не менять при ошибке.
    lock_promo_row: при оформлении заказа — блокировка строки Promocode (FOR UPDATE), чтобы
    max_uses_total не превышался при одновременных чекаутах; для preview не использовать.
    exchange_rate + delivery_cost_per_kg: если задан курс, скидка по строке не опускает сумму
    ниже себестоимости (юань×курс + доставка по весу, без сервисного сбора).
    """
    raw = (promo_code or "").strip()
    if not raw:
        return lines, Decimal(0), None
    if _STORE_KP_LITE:
        return lines, Decimal(0), None

    norm = normalize_promo_code(raw)
    st = await session.get(SystemPhotoPromoSettings, 1)

    use_system = (
        st
        and st.is_enabled
        and (st.current_code_normalized or "").strip()
        and norm == (st.current_code_normalized or "").strip().upper()
    )

    promo: Optional[Promocode] = None
    redemption_kind: str = "system"
    admin_promo_id: Optional[int] = None
    usage_kind: str = "multi"
    pool_item_ids: Optional[set] = None
    scoped_admin: set = set()

    if use_system:
        pct = _effective_percent(st.discount_percent)
        pool_item_ids = await _system_pool_item_ids(session)
    else:
        stmt = select(Promocode).where(
            Promocode.code_normalized == norm,
            Promocode.is_active == True,  # noqa: E712
        )
        if lock_promo_row:
            stmt = stmt.with_for_update()
        pr = await session.execute(stmt)
        promo = pr.scalar_one_or_none()
        if not promo:
            return lines, Decimal(0), "Промокод не найден или неактивен"
        if promo.expires_at is not None:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            exp = promo.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                return lines, Decimal(0), "Срок действия промокода истёк"
        pct = _effective_percent(promo.discount_percent)
        redemption_kind = "admin"
        admin_promo_id = promo.id
        usage_kind = (promo.usage_kind or "multi").strip()
        if promo.scope_all:
            pool_item_ids = None
        else:
            ir = await session.execute(
                select(PromocodeItem.item_id).where(PromocodeItem.promocode_id == promo.id)
            )
            scoped_admin = {row[0] for row in ir.all()}
            pool_item_ids = set(scoped_admin)
            if not bool(getattr(promo, "pool_is_blacklist", False)) and not pool_item_ids:
                return lines, Decimal(0), "Промокод ни на какие товары не распространяется"

        if promo.max_uses_total is not None:
            used = await _admin_promo_total_orders(promo.id, session)
            if used >= promo.max_uses_total:
                return lines, Decimal(0), "Лимит использований промокода исчерпан"

        if usage_kind == "once_per_user":
            uused = await _admin_promo_user_orders(promo.id, user_id, session)
            if uused >= 1:
                return lines, Decimal(0), "Вы уже использовали этот промокод"
        elif promo.max_uses_per_user is not None:
            uused = await _admin_promo_user_orders(promo.id, user_id, session)
            if uused >= promo.max_uses_per_user:
                return lines, Decimal(0), "Вы уже использовали этот промокод"

    item_by_id: Dict[int, Item] = {}
    if exchange_rate is not None:
        iids = {int(line.get("item_id") or 0) for line in lines}
        iids.discard(0)
        if iids:
            ir = await session.execute(select(Item).where(Item.id.in_(iids)))
            item_by_id = {i.id: i for i in ir.scalars().all()}

    out_lines: List[Dict[str, Any]] = []
    total_disc = Decimal(0)
    any_discount = False

    for line in lines:
        row = dict(line)
        iid = int(row.get("item_id") or 0)
        qty = max(1, int(row.get("quantity") or 1))
        unit = Decimal(str(row.get("price") or 0))
        line_subtotal = unit * qty

        eligible = True
        if use_system:
            if pool_item_ids is None:
                eligible = True
            elif bool(getattr(st, "pool_is_blacklist", False)):
                eligible = iid not in pool_item_ids
            else:
                eligible = iid in pool_item_ids
        elif promo is not None:
            if promo.scope_all:
                eligible = True
            elif bool(getattr(promo, "pool_is_blacklist", False)):
                eligible = iid not in scoped_admin
            else:
                eligible = iid in scoped_admin

        skip_unique = False
        if eligible and use_system:
            if await _line_already_used_system(iid, session):
                skip_unique = True
        elif eligible and promo and usage_kind == "unique_per_item":
            if await _line_already_used_admin_unique(promo.id, iid, session):
                skip_unique = True

        if not eligible or skip_unique or line_subtotal <= 0:
            out_lines.append(row)
            continue

        disc = (line_subtotal * pct / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        item = item_by_id.get(iid) if exchange_rate is not None else None
        if item is not None:
            ymk = yuan_markup_before_rub_percent if yuan_markup_before_rub_percent is not None else Decimal(0)
            floor_unit = item_sebestoimost_rub(
                item, exchange_rate, delivery_cost_per_kg, yuan_markup_before_rub_percent=ymk
            )
            floor_subtotal = (floor_unit * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            max_disc = (line_subtotal - floor_subtotal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if max_disc < Decimal("0"):
                max_disc = Decimal("0")
            if disc > max_disc:
                disc = max_disc
        if disc <= 0:
            out_lines.append(row)
            continue

        new_subtotal = line_subtotal - disc
        new_unit = (new_subtotal / qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        row["original_unit_price_rub"] = float(unit)
        row["price"] = float(new_unit)
        row["promo_discount_rub"] = float(disc)
        row["promo_redemption_kind"] = redemption_kind
        row["promo_admin_id"] = admin_promo_id
        row["promo_code_snapshot"] = code_snapshot[:64]
        if redemption_kind == "system":
            row["photo_promo_line"] = True
        total_disc += disc
        any_discount = True
        out_lines.append(row)

    if not any_discount and raw:
        return lines, Decimal(0), "Промокод не применим к товарам в корзине"

    return out_lines, total_disc, None


async def ensure_system_photo_promo_seed(session: AsyncSession) -> None:
    st = await session.get(SystemPhotoPromoSettings, 1)
    if st is None:
        session.add(
            SystemPhotoPromoSettings(
                id=1,
                is_enabled=False,
                discount_percent=Decimal("10"),
                current_code_normalized="",
                badge_label="Скидка за наше фото",
            )
        )
        await session.commit()
