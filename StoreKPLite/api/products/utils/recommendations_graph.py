from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.models.item_compatibility_edge import ItemCompatibilityEdge
from api.products.models.item_style_profile import ItemStyleProfile

NEUTRALS = frozenset({"neutral_black", "neutral_white", "neutral_gray", "neutral_beige"})
COLOR_ORDER = [
    "red",
    "orange",
    "yellow",
    "lime",
    "green",
    "cyan",
    "blue",
    "indigo",
    "violet",
    "magenta",
    "pink",
]
CHROMATIC = frozenset(COLOR_ORDER)

_BLACK_WITH_HUE: Dict[str, float] = {
    "red": 0.72, "orange": 0.74, "yellow": 0.79, "lime": 0.64, "green": 0.62,
    "cyan": 0.63, "blue": 0.66, "indigo": 0.65, "violet": 0.58, "magenta": 0.55, "pink": 0.55,
}
_WHITE_WITH_HUE: Dict[str, float] = {
    "red": 0.84, "orange": 0.86, "yellow": 0.90, "lime": 0.78, "green": 0.76,
    "cyan": 0.80, "blue": 0.82, "indigo": 0.80, "violet": 0.78, "magenta": 0.85, "pink": 0.87,
}
_GRAY_WITH_HUE: Dict[str, float] = {h: min(0.93, _BLACK_WITH_HUE[h] + 0.14) for h in COLOR_ORDER}
_BEIGE_WITH_HUE: Dict[str, float] = {
    "red": 0.78, "orange": 0.86, "yellow": 0.88, "lime": 0.72, "green": 0.70,
    "cyan": 0.74, "blue": 0.72, "indigo": 0.72, "violet": 0.68, "magenta": 0.72, "pink": 0.76,
}
_NEUTRAL_NEUTRAL = {
    frozenset({"neutral_black"}): 0.97,
    frozenset({"neutral_black", "neutral_gray"}): 0.92,
    frozenset({"neutral_black", "neutral_white"}): 0.86,
    frozenset({"neutral_black", "neutral_beige"}): 0.80,
    frozenset({"neutral_gray"}): 0.95,
    frozenset({"neutral_gray", "neutral_white"}): 0.91,
    frozenset({"neutral_gray", "neutral_beige"}): 0.90,
    frozenset({"neutral_white"}): 0.97,
    frozenset({"neutral_white", "neutral_beige"}): 0.92,
    frozenset({"neutral_beige"}): 0.95,
}


def guess_slot_from_item_type(item_type_name: str) -> str:
    n = (item_type_name or "").strip().lower()
    exact = {
        "кроссовки": "footwear", "футболки": "body_l1", "лонгсливы": "body_l1",
        "худи": "body_l2", "джемперы": "body_l2", "свитера": "body_l2", "рюкзаки": "body_l2",
        "куртки": "body_l3", "джинсы": "legs", "штаны": "legs", "шорты": "legs",
        "аксессуары": "head",
    }
    if n in exact:
        return exact[n]
    return "unknown"


def _normalize_color_profile(profile: Dict[str, float]) -> Dict[str, float]:
    if not profile:
        return {"neutral_gray": 1.0}
    out = {k: max(0.0, float(v)) for k, v in (profile or {}).items() if float(v) > 1e-9}
    s = sum(out.values())
    if s < 1e-9:
        return {"neutral_gray": 1.0}
    return {k: v / s for k, v in out.items()}


def _color_distance_steps(c1: str, c2: str) -> int:
    try:
        i1 = COLOR_ORDER.index(c1)
        i2 = COLOR_ORDER.index(c2)
    except ValueError:
        return 5
    d = abs(i1 - i2)
    return min(d, len(COLOR_ORDER) - d)


def _pair_bucket_score(c1: str, c2: str) -> float:
    n1, n2 = c1 in NEUTRALS, c2 in NEUTRALS
    if n1 and n2:
        return float(_NEUTRAL_NEUTRAL.get(frozenset({c1, c2}), 0.88))
    if n1 or n2:
        neutral, hue = (c1, c2) if n1 else (c2, c1)
        if hue not in CHROMATIC:
            return 0.72
        if neutral == "neutral_black":
            return float(_BLACK_WITH_HUE.get(hue, 0.65))
        if neutral == "neutral_white":
            return float(_WHITE_WITH_HUE.get(hue, 0.82))
        if neutral == "neutral_gray":
            return float(_GRAY_WITH_HUE.get(hue, 0.72))
        if neutral == "neutral_beige":
            return float(_BEIGE_WITH_HUE.get(hue, 0.76))
        return 0.72
    d = _color_distance_steps(c1, c2)
    if d <= 1:
        return 0.88
    if d in (3, 4):
        return 0.82
    if d == 5:
        return 0.85
    if d == 2:
        return 0.65
    return 0.55


def color_compatibility(a: Dict[str, float], b: Dict[str, float]) -> float:
    pa = _normalize_color_profile(a)
    pb = _normalize_color_profile(b)
    total = 0.0
    for k1, w1 in pa.items():
        for k2, w2 in pb.items():
            total += float(w1) * float(w2) * _pair_bucket_score(k1, k2)
    return float(min(1.0, max(0.0, total)))


def style_cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = set((a or {}).keys()) | set((b or {}).keys())
    if not keys:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for k in keys:
        va = float((a or {}).get(k, 0.0))
        vb = float((b or {}).get(k, 0.0))
        dot += va * vb
        na += va * va
        nb += vb * vb
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return float(dot / ((na ** 0.5) * (nb ** 0.5)))


@dataclass
class RebuildResult:
    item_count: int
    edge_count: int


async def rebuild_compatibility_graph(
    session: AsyncSession,
    min_score: float = 0.45,
    top_k_per_item: int = 40,
) -> RebuildResult:
    rows = (await session.execute(select(ItemStyleProfile))).scalars().all()
    by_id = {int(r.item_id): r for r in rows if r.style_vector and r.slot and r.slot != "unknown"}
    ids = list(by_id.keys())
    out: Dict[int, List[ItemCompatibilityEdge]] = {i: [] for i in ids}

    for i in range(len(ids)):
        a = by_id[ids[i]]
        for j in range(i + 1, len(ids)):
            b = by_id[ids[j]]
            if a.slot == b.slot:
                continue
            s_style = style_cosine(a.style_vector or {}, b.style_vector or {})
            s_color = color_compatibility(a.color_wheel_profile or {}, b.color_wheel_profile or {})
            score = float(s_style) * float(s_color)
            if score < float(min_score):
                continue
            score_d = Decimal(f"{score:.6f}")
            style_d = Decimal(f"{s_style:.6f}")
            color_d = Decimal(f"{s_color:.6f}")
            out[a.item_id].append(ItemCompatibilityEdge(
                from_item_id=a.item_id, to_item_id=b.item_id, score=score_d, style_score=style_d, color_score=color_d
            ))
            out[b.item_id].append(ItemCompatibilityEdge(
                from_item_id=b.item_id, to_item_id=a.item_id, score=score_d, style_score=style_d, color_score=color_d
            ))

    await session.execute(delete(ItemCompatibilityEdge))
    edge_count = 0
    for item_id, edges in out.items():
        top = sorted(edges, key=lambda x: float(x.score), reverse=True)[: max(1, int(top_k_per_item))]
        edge_count += len(top)
        session.add_all(top)
    await session.commit()
    return RebuildResult(item_count=len(ids), edge_count=edge_count)
