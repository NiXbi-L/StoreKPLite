"""Снимки онлайна: средний онлайн по часу суток за последние N дней."""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def hourly_avg_online_last_days(session: AsyncSession, days: int = 30) -> List[float]:
    """
    24 значения (час 0..23, локальное время Asia/Vladivostok): средний online_count за период.
    Часов без данных — 0.0.
    """
    q = text(
        """
        SELECT EXTRACT(HOUR FROM (recorded_at AT TIME ZONE 'Asia/Vladivostok'))::int AS hr,
               AVG(online_count)::double precision AS av
        FROM online_snapshots
        WHERE recorded_at >= NOW() - (INTERVAL '1 day' * CAST(:days AS int))
        GROUP BY 1
        ORDER BY 1
        """
    )
    rows = (await session.execute(q, {"days": max(1, int(days))})).all()
    out = [0.0] * 24
    for hr, av in rows:
        h = int(hr)
        if 0 <= h < 24 and av is not None:
            out[h] = round(float(av), 2)
    return out


async def online_block_for_dashboard(session: AsyncSession) -> Dict[str, Any]:
    from api.users.services.online_presence import count_users_active_within_seconds, count_users_online

    current = await count_users_online()
    hourly = await hourly_avg_online_last_days(session, 30)
    seven_days_sec = 7 * 24 * 3600
    active_last_7d = await count_users_active_within_seconds(seven_days_sec)
    return {
        "current": int(current),
        "active_last_7d": int(active_last_7d),
        "hourly_avg_vladivostok_30d": hourly,
    }
