from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.database.database import get_session
from api.products.models.item import Item
from api.products.models.item_compatibility_edge import ItemCompatibilityEdge
from api.products.models.item_photo import ItemPhoto
from api.products.models.item_price_history import ItemPriceHistory
from api.products.models.item_stock import ItemStock
from api.products.models.item_style_profile import ItemStyleProfile
from api.products.schemas.item import CatalogPageResponse, FeedItemResponse, ItemPhotoResponse
from api.products.utils.finance_context import get_finance_price_context, FinancePriceContext
from api.products.utils.customer_price_context import finance_ctx_with_owner_display
from api.products.utils.item_pricing import compute_item_unit_price_for_ctx
from api.products.utils.promo_apply import batch_system_photo_promo_badges
from api.products.utils.feed_like_counts import get_feed_like_dislike_counts_map, like_dislike_for
from api.products.utils.recommendations_graph import (
    guess_slot_from_item_type,
    rebuild_compatibility_graph,
)
from api.shared.admin_permissions import has_admin_permission
from api.shared.auth import get_user_id_for_request, verify_jwt_token
from api.shared.timezone import now_vladivostok

logger = logging.getLogger(__name__)
router = APIRouter()
REDIS_URL = os.getenv("REDIS_URL", "redis://products-redis:6379/0")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")
admin_bearer = HTTPBearer(auto_error=False)


def _is_internal_token_valid(token: Optional[str]) -> bool:
    if not token:
        return False
    clean = token.replace("Bearer ", "").strip() if str(token).startswith("Bearer ") else str(token).strip()
    return bool(clean) and clean == INTERNAL_TOKEN


async def require_internal_or_catalog_admin(
    request: Request,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(admin_bearer),
) -> dict:
    if _is_internal_token_valid(x_internal_token):
        return {"auth": "internal"}
    token: Optional[str] = None
    if credentials is not None and credentials.credentials:
        token = credentials.credentials.strip() or None
    if not token:
        auth = request.headers.get("Authorization") or request.headers.get("authorization") or ""
        if isinstance(auth, str) and auth.startswith("Bearer "):
            token = auth[7:].strip() or None
    if not token:
        token = (request.cookies.get("admin_access_token") or "").strip() or None
    if not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    bearer_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    payload = await verify_jwt_token(bearer_creds)
    if has_admin_permission(payload, "catalog"):
        return {"auth": "admin_jwt", "payload": payload}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")


class StyleProfileIn(BaseModel):
    item_id: int
    item_type_name: Optional[str] = None
    slot: Optional[str] = None
    top_styles: Optional[List[str]] = None
    style_vector: Dict[str, float]
    color_wheel_profile: Optional[Dict[str, float]] = None


class StyleProfilesBulkIn(BaseModel):
    items: List[StyleProfileIn] = Field(default_factory=list)


class GraphRebuildRequest(BaseModel):
    min_score: float = 0.45
    top_k_per_item: int = 40


def _calculate_item_price_local(item: Item, ctx: FinancePriceContext) -> Decimal:
    return compute_item_unit_price_for_ctx(item, ctx)


@router.post("/admin/recommendations/style-profiles/upsert")
async def upsert_style_profiles(
    payload: StyleProfilesBulkIn,
    _auth=Depends(require_internal_or_catalog_admin),
    session: AsyncSession = Depends(get_session),
):
    if not payload.items:
        return {"upserted": 0, "skipped": 0}
    rows = []
    for rec in payload.items:
        slot = (rec.slot or "").strip() or guess_slot_from_item_type(rec.item_type_name or "")
        rows.append({
            "item_id": rec.item_id,
            "slot": slot or "unknown",
            "item_type_name": rec.item_type_name,
            "top_styles": rec.top_styles or [],
            "style_vector": rec.style_vector or {},
            "color_wheel_profile": rec.color_wheel_profile or {},
        })
    candidate_ids = [int(r["item_id"]) for r in rows]
    existing_item_rows = (
        await session.execute(select(Item.id).where(Item.id.in_(candidate_ids)))
    ).all()
    existing_ids = {int(x[0]) for x in existing_item_rows}
    rows = [r for r in rows if int(r["item_id"]) in existing_ids]
    skipped = len(candidate_ids) - len(rows)
    if not rows:
        return {"upserted": 0, "skipped": skipped}
    stmt = insert(ItemStyleProfile).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[ItemStyleProfile.item_id],
        set_={
            "slot": stmt.excluded.slot,
            "item_type_name": stmt.excluded.item_type_name,
            "top_styles": stmt.excluded.top_styles,
            "style_vector": stmt.excluded.style_vector,
            "color_wheel_profile": stmt.excluded.color_wheel_profile,
            "updated_at": now_vladivostok(),
        },
    )
    await session.execute(stmt)
    await session.commit()
    return {"upserted": len(rows), "skipped": skipped}


@router.post("/admin/recommendations/graph/rebuild")
async def rebuild_graph(
    payload: GraphRebuildRequest,
    _auth=Depends(require_internal_or_catalog_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await rebuild_compatibility_graph(
        session=session,
        min_score=payload.min_score,
        top_k_per_item=payload.top_k_per_item,
    )
    try:
        import redis.asyncio as redis

        client = await redis.from_url(REDIS_URL, decode_responses=True)
        keys = []
        async for key in client.scan_iter(match="item:recommendations:*"):
            keys.append(key)
        if keys:
            await client.delete(*keys)
        await client.close()
    except Exception as e:
        logger.debug("Recommendations cache invalidation skip: %s", e)
    return {"items": result.item_count, "edges": result.edge_count}


@router.get("/items/{item_id}/recommendations", response_model=CatalogPageResponse)
async def get_item_recommendations(
    item_id: int,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    platform_id: Optional[str] = Header(None, alias="X-Platform-Id"),
    platform: Optional[str] = Header(None, alias="X-Platform"),
    session: AsyncSession = Depends(get_session),
):
    user_id: Optional[int] = None
    if authorization or x_internal_token:
        try:
            user_id = await get_user_id_for_request(
                authorization=authorization,
                x_internal_token=x_internal_token,
                platform_id=platform_id,
                platform=platform,
            )
        except HTTPException as exc:
            if exc.status_code not in (401, 403):
                raise
            user_id = None

    cache_key = f"item:recommendations:v1:{item_id}"
    all_ids: List[int] = []
    try:
        import redis.asyncio as redis

        client = await redis.from_url(REDIS_URL, decode_responses=True)
        cached = await client.get(cache_key)
        if cached:
            data = json.loads(cached)
            all_ids = [int(x) for x in (data.get("item_ids") or [])]
        else:
            edge_rows = (await session.execute(
                select(ItemCompatibilityEdge.to_item_id)
                .where(ItemCompatibilityEdge.from_item_id == item_id)
                .order_by(ItemCompatibilityEdge.score.desc())
            )).all()
            all_ids = [int(r[0]) for r in edge_rows]
            await client.setex(cache_key, 86400, json.dumps({"item_ids": all_ids}))
        await client.close()
    except Exception:
        edge_rows = (await session.execute(
            select(ItemCompatibilityEdge.to_item_id)
            .where(ItemCompatibilityEdge.from_item_id == item_id)
            .order_by(ItemCompatibilityEdge.score.desc())
        )).all()
        all_ids = [int(r[0]) for r in edge_rows]

    total = len(all_ids)
    page_ids = all_ids[offset: offset + limit]
    if not page_ids:
        return CatalogPageResponse(items=[], total=total, has_more=False, next_offset=None)
    order_case = case({id_: i for i, id_ in enumerate(page_ids)}, value=Item.id)
    items = (await session.execute(select(Item).where(Item.id.in_(page_ids)).order_by(order_case))).scalars().all()
    item_ids = [x.id for x in items]

    photos = (await session.execute(
        select(ItemPhoto).where(ItemPhoto.item_id.in_(item_ids)).order_by(ItemPhoto.item_id, ItemPhoto.sort_order, ItemPhoto.id)
    )).scalars().all()
    photos_by_item: Dict[int, List[ItemPhoto]] = {}
    for p in photos:
        photos_by_item.setdefault(int(p.item_id), []).append(p)

    stock_rows = (await session.execute(
        select(ItemStock.item_id).where(and_(ItemStock.item_id.in_(item_ids), ItemStock.quantity > 0)).distinct()
    )).all()
    items_with_stock = {int(r[0]) for r in stock_rows}

    likes = set()
    if user_id is not None and item_ids:
        from api.products.models.like import Like
        likes_rows = (await session.execute(
            select(Like.item_id).where(and_(Like.user_id == user_id, Like.action == "like", Like.item_id.in_(item_ids)))
        )).all()
        likes = {int(r[0]) for r in likes_rows}

    cutoff = now_vladivostok() - timedelta(days=7)
    hist_rows = (await session.execute(
        select(ItemPriceHistory.item_id, ItemPriceHistory.min_price, ItemPriceHistory.max_price)
        .where(and_(ItemPriceHistory.item_id.in_(item_ids), ItemPriceHistory.week_start >= cutoff))
    )).all()
    minmax: Dict[int, tuple[Any, Any]] = {}
    for row in hist_rows:
        iid = int(row[0])
        cur = minmax.get(iid)
        mn, mx = row[1], row[2]
        if cur is None:
            minmax[iid] = (mn, mx)
        else:
            minmax[iid] = (min(cur[0], mn), max(cur[1], mx))

    badges = await batch_system_photo_promo_badges(session, item_ids)
    counts_map = await get_feed_like_dislike_counts_map(session, item_ids)
    ctx = await finance_ctx_with_owner_display(await get_finance_price_context(), authorization)
    out: List[FeedItemResponse] = []
    for item in items:
        price_rub = _calculate_item_price_local(item, ctx)
        mn, mx = minmax.get(item.id, (price_rub, price_rub))
        item_photos = photos_by_item.get(item.id, [])
        size_str = ", ".join(str(s) for s in item.size) if isinstance(item.size, list) else (str(item.size) if item.size else None)
        lc, dc = like_dislike_for(counts_map, item.id)
        out.append(FeedItemResponse(
            id=item.id,
            name=item.name,
            description=item.description,
            price_rub=price_rub,
            size=size_str,
            min_price_week=mn,
            max_price_week=mx,
            telegram_file_id=item_photos[0].telegram_file_id if item_photos else None,
            vk_attachment=item_photos[0].vk_attachment if item_photos else None,
            photos=[ItemPhotoResponse(
                id=p.id,
                file_path=p.file_path,
                telegram_file_id=p.telegram_file_id,
                vk_attachment=p.vk_attachment,
                sort_order=getattr(p, "sort_order", 0),
            ) for p in item_photos],
            group_id=item.group_id,
            group_name=None,
            group_items=[],
            is_group=False,
            is_legit=item.is_legit,
            liked=item.id in likes if user_id is not None else None,
            fixed_price_rub=getattr(item, "fixed_price", None) if item.id in items_with_stock else None,
            photo_promo_badge=badges.get(item.id),
            feed_like_count=lc,
            feed_dislike_count=dc,
        ))

    has_more = total > (offset + limit)
    return CatalogPageResponse(items=out, total=total, has_more=has_more, next_offset=(offset + limit) if has_more else None)
