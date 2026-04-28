"""Агрегация реферальных начислений по завершённым заказам."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.models.order import Order


def month_start_utc(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=timezone.utc)


def next_month_start_utc(year: int, month: int) -> datetime:
    if month == 12:
        return datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(year, month + 1, 1, tzinfo=timezone.utc)


def current_month_bounds_utc(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    start = month_start_utc(now.year, now.month)
    end = next_month_start_utc(now.year, now.month)
    return start, end


def iter_past_month_starts(count: int, now: Optional[datetime] = None) -> List[Tuple[datetime, datetime, str]]:
    """Последние `count` месяцев (включая текущий): (start, end, 'YYYY-MM')."""
    now = now or datetime.now(timezone.utc)
    out: List[Tuple[datetime, datetime, str]] = []
    y, m = now.year, now.month
    for _ in range(count):
        start = month_start_utc(y, m)
        end = next_month_start_utc(y, m)
        out.append((start, end, f"{y:04d}-{m:02d}"))
        if m == 1:
            y -= 1
            m = 12
        else:
            m -= 1
    return out


def _commission_from_snapshot(order: Order) -> Optional[Tuple[int, int, Decimal, Decimal]]:
    """(referrer_user_id, promocode_id, service_fee_base_rub, commission_rub) или None."""
    data = order.order_data or {}
    snap = data.get("referral_snapshot")
    if not isinstance(snap, dict):
        return None
    try:
        rid = int(snap["referrer_user_id"])
        pid = int(snap["promocode_id"])
        base = Decimal(str(snap["service_fee_base_rub"]))
        pct = Decimal(str(snap["commission_percent"]))
    except (KeyError, TypeError, ValueError):
        return None
    comm = (base * pct / Decimal("100")).quantize(Decimal("0.01"))
    return rid, pid, base, comm


async def aggregate_referral_by_promocode_for_range(
    session: AsyncSession,
    start: datetime,
    end: datetime,
) -> Dict[int, Tuple[int, Decimal]]:
    """promocode_id -> (завершённых заказов, сумма комиссии ₽)."""
    r = await session.execute(
        select(Order).where(
            Order.status == "завершен",
            Order.created_at >= start,
            Order.created_at < end,
        )
    )
    acc: Dict[int, list] = defaultdict(lambda: [0, Decimal("0")])
    for o in r.scalars().all():
        parsed = _commission_from_snapshot(o)
        if not parsed:
            continue
        _, pid, _, comm = parsed
        acc[pid][0] += 1
        acc[pid][1] += comm
    return {k: (int(v[0]), v[1]) for k, v in acc.items()}


async def aggregate_referral_for_referrer_in_range(
    session: AsyncSession,
    referrer_user_id: int,
    start: datetime,
    end: datetime,
) -> Tuple[int, Decimal]:
    """Число завершённых заказов и сумма комиссии для владельца за период."""
    r = await session.execute(
        select(Order).where(
            Order.status == "завершен",
            Order.created_at >= start,
            Order.created_at < end,
        )
    )
    n = 0
    total = Decimal("0")
    for o in r.scalars().all():
        parsed = _commission_from_snapshot(o)
        if not parsed or parsed[0] != referrer_user_id:
            continue
        n += 1
        total += parsed[3]
    return n, total
