"""Батч-подсчёт лайков/дизлайков ленты по товарам (таблица likes)."""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.models.like import Like


async def get_feed_like_dislike_counts_map(session: AsyncSession, item_ids: Sequence[int]) -> Dict[int, Tuple[int, int]]:
    """
    Возвращает для каждого item_id кортеж (likes, dislikes) только по action like/dislike.
    Товары без строк в likes не попадают в dict — считать как (0, 0).
    """
    ids = [int(i) for i in item_ids if i is not None]
    if not ids:
        return {}
    likes_sum = func.coalesce(
        func.sum(case((Like.action == "like", 1), else_=0)),
        0,
    ).label("likes")
    dislikes_sum = func.coalesce(
        func.sum(case((Like.action == "dislike", 1), else_=0)),
        0,
    ).label("dislikes")
    result = await session.execute(
        select(Like.item_id, likes_sum, dislikes_sum)
        .where(Like.item_id.in_(ids))
        .group_by(Like.item_id)
    )
    out: Dict[int, Tuple[int, int]] = {}
    for row in result.all():
        iid = int(row[0])
        out[iid] = (int(row[1] or 0), int(row[2] or 0))
    return out


def like_dislike_for(map_: Dict[int, Tuple[int, int]], item_id: int) -> Tuple[int, int]:
    return map_.get(int(item_id), (0, 0))
