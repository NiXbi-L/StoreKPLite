"""
Ранжирование ленты: глобальный тренд (лайки−дизлайки), граф сочетаемости, стиль по лайкам,
мягкие штрафы за группу/тип после дизлайка, без подряд одной item_groups.
Правила мягкие: при отсутствии альтернатив допускается повтор группы.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.models.item import Item
from api.products.models.item_compatibility_edge import ItemCompatibilityEdge
from api.products.models.item_style_profile import ItemStyleProfile
from api.products.models.like import Like
from api.products.utils.feed_like_counts import get_feed_like_dislike_counts_map
from api.products.utils.recommendations_graph import style_cosine

# Веса — мягкие; суммарный сдвиг ограничен, чтобы каталог «доигрывался» до конца.
W_TREND = 0.24
W_COMPAT = 0.26
W_LIKE_STYLE = 0.20
W_TOP_STYLE_TAGS = 0.10
W_DISLIKE_STYLE = 0.10
TREND_TANH_DIV = 7.0
GROUP_DISLIKE_MUL = 0.94
TYPE_DISLIKE_MUL = 0.93
SCORE_NOISE = 0.012


def _avg_style_vectors(rows: Sequence[ItemStyleProfile]) -> Dict[str, float]:
    if not rows:
        return {}
    acc: Dict[str, float] = {}
    for r in rows:
        sv = r.style_vector or {}
        if not isinstance(sv, dict):
            continue
        for k, v in sv.items():
            try:
                acc[str(k)] = acc.get(str(k), 0.0) + float(v)
            except (TypeError, ValueError):
                continue
    n = float(len(rows))
    if n < 1e-9:
        return {}
    return {k: v / n for k, v in acc.items()}


def _top_style_names_from_likes(rows: Sequence[ItemStyleProfile], k: int = 3) -> List[str]:
    """Имена стилей из top_styles лайкнутых вещей (частоты)."""
    c: Counter[str] = Counter()
    for r in rows:
        ts = r.top_styles
        if not ts:
            continue
        if isinstance(ts, list):
            for x in ts:
                if x:
                    c[str(x).strip().lower()] += 1
        elif isinstance(ts, str):
            c[ts.strip().lower()] += 1
    return [s for s, _ in c.most_common(k)]


def _tag_boost(style_vector: Dict[str, float], top_names: Sequence[str]) -> float:
    if not top_names or not style_vector:
        return 0.0
    vals = []
    for name in top_names:
        key = name.strip().lower()
        v = 0.0
        for sk, sv in style_vector.items():
            if str(sk).strip().lower() == key:
                try:
                    v = max(v, float(sv))
                except (TypeError, ValueError):
                    pass
        vals.append(v)
    return float(sum(vals) / max(len(vals), 1))


def _trend_norm(margin: int) -> float:
    return math.tanh(float(margin) / TREND_TANH_DIV)


_NO_LAST_GROUP = object()


def greedy_pick_by_group(
    scored: List[Tuple[int, float, Optional[int]]],
    limit: int,
) -> List[int]:
    """
    scored: (item_id, score, group_id) отсортированы по score убыв.
    Не ставим подряд две вещи с одинаковым group_id (если group_id не None).
    """
    remaining = list(scored)
    out: List[int] = []
    last_gid: object | int | None = _NO_LAST_GROUP

    while len(out) < limit and remaining:
        chosen_i = None
        for i, (_iid, _sc, gid) in enumerate(remaining):
            if last_gid is _NO_LAST_GROUP or gid is None or gid != last_gid:
                chosen_i = i
                break
        if chosen_i is None:
            chosen_i = 0
        iid, _sc, gid = remaining.pop(chosen_i)
        out.append(iid)
        last_gid = gid
    return out


async def compute_personalized_scores(
    session: AsyncSession,
    user_id: Optional[int],
    candidate_ids: List[int],
    *,
    add_noise: bool,
) -> List[Tuple[int, float, Optional[int]]]:
    """
    Те же сигналы, что и для ленты (тренд, граф от лайков, стиль, дизлайки).
    Возвращает (item_id, raw, group_id) в порядке обхода candidate_ids (без сортировки).
    """
    if not candidate_ids:
        return []

    cid_set = list(dict.fromkeys(int(x) for x in candidate_ids))

    items_res = await session.execute(
        select(Item.id, Item.group_id, Item.item_type_id).where(Item.id.in_(cid_set))
    )
    item_rows = items_res.all()
    id_to_group: Dict[int, Optional[int]] = {}
    id_to_type: Dict[int, int] = {}
    for row in item_rows:
        iid = int(row[0])
        id_to_group[iid] = int(row[1]) if row[1] is not None else None
        id_to_type[iid] = int(row[2]) if row[2] is not None else 0

    prof_res = await session.execute(
        select(ItemStyleProfile).where(ItemStyleProfile.item_id.in_(cid_set))
    )
    profiles = {int(p.item_id): p for p in prof_res.scalars().all()}

    counts_map = await get_feed_like_dislike_counts_map(session, cid_set)

    liked_ids: List[int] = []
    disliked_item_ids: List[int] = []
    if user_id is not None:
        lr = await session.execute(
            select(Like.item_id, Like.action).where(
                Like.user_id == user_id,
                Like.action.in_(["like", "dislike"]),
            )
        )
        for iid, act in lr.all():
            if act == "like":
                liked_ids.append(int(iid))
            else:
                disliked_item_ids.append(int(iid))

    liked_profiles: List[ItemStyleProfile] = []
    if liked_ids:
        lp = await session.execute(
            select(ItemStyleProfile).where(ItemStyleProfile.item_id.in_(liked_ids))
        )
        liked_profiles = list(lp.scalars().all())

    dislike_centroid: Dict[str, float] = {}
    bad_groups: set[int] = set()
    bad_types: set[int] = set()
    disliked_top_names: List[str] = []

    if user_id is not None and disliked_item_ids:
        dp = await session.execute(
            select(ItemStyleProfile).where(ItemStyleProfile.item_id.in_(disliked_item_ids))
        )
        dis_prof = list(dp.scalars().all())
        dislike_centroid = _avg_style_vectors(dis_prof)
        disliked_top_names = _top_style_names_from_likes(dis_prof, k=3)

        ir = await session.execute(
            select(Item.group_id, Item.item_type_id).where(Item.id.in_(disliked_item_ids))
        )
        for gid, tid in ir.all():
            if gid is not None:
                bad_groups.add(int(gid))
            if tid is not None:
                bad_types.add(int(tid))

    like_centroid = _avg_style_vectors(liked_profiles)
    user_top_tags = _top_style_names_from_likes(liked_profiles, k=3)

    compat_by_to: Dict[int, float] = {}
    if liked_ids and cid_set:
        ce = await session.execute(
            select(ItemCompatibilityEdge.to_item_id, func.max(ItemCompatibilityEdge.score)).where(
                ItemCompatibilityEdge.from_item_id.in_(liked_ids),
                ItemCompatibilityEdge.to_item_id.in_(cid_set),
            ).group_by(ItemCompatibilityEdge.to_item_id)
        )
        for to_id, mx in ce.all():
            compat_by_to[int(to_id)] = float(mx or 0.0)

    scored: List[Tuple[int, float, Optional[int]]] = []

    for iid in cid_set:
        likes_c, dis_c = counts_map.get(iid, (0, 0))
        margin = int(likes_c) - int(dis_c)
        trend = _trend_norm(margin)

        prof = profiles.get(iid)
        sv = (prof.style_vector if prof else None) or {}
        if not isinstance(sv, dict):
            sv = {}

        cos_like = style_cosine(like_centroid, sv) if like_centroid else 0.0
        cos_dislike = style_cosine(dislike_centroid, sv) if dislike_centroid else 0.0
        compat = compat_by_to.get(iid, 0.0)
        tag_b = _tag_boost(sv, user_top_tags)
        tag_pen = _tag_boost(sv, disliked_top_names)

        gid = id_to_group.get(iid)
        tid = id_to_type.get(iid, 0)

        raw = (
            1.0
            + W_TREND * trend
            + W_COMPAT * compat
            + W_LIKE_STYLE * cos_like
            + W_TOP_STYLE_TAGS * tag_b
            - W_DISLIKE_STYLE * cos_dislike
            - 0.5 * W_TOP_STYLE_TAGS * tag_pen
        )

        if gid is not None and gid in bad_groups:
            raw *= GROUP_DISLIKE_MUL
        if tid and tid in bad_types:
            raw *= TYPE_DISLIKE_MUL

        if add_noise:
            raw += random.uniform(-SCORE_NOISE, SCORE_NOISE)
        scored.append((iid, raw, gid))

    return scored


async def rank_catalog_by_personalization(
    session: AsyncSession,
    user_id: int,
    candidate_ids: List[int],
) -> List[int]:
    """
    Полный порядок id для каталога без текстового поиска: как лента, но без шума и без
    greedy по группам — стабильная пагинация по убыванию скора (при равенстве — id).
    """
    scored = await compute_personalized_scores(session, user_id, candidate_ids, add_noise=False)
    scored.sort(key=lambda x: (-x[1], -x[0]))
    return [t[0] for t in scored]


async def rank_feed_candidates(
    session: AsyncSession,
    user_id: Optional[int],
    candidate_ids: List[int],
    limit: int,
) -> List[int]:
    if not candidate_ids:
        return []
    if limit < 1:
        return []

    scored = await compute_personalized_scores(session, user_id, candidate_ids, add_noise=True)
    scored.sort(key=lambda x: -x[1])
    return greedy_pick_by_group(scored, limit)
