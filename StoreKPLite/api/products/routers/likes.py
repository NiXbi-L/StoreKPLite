"""
Роутер для получения списка лайков/дизлайков/сохраненных
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from api.products.database.database import get_session
from api.products.models.item import Item
from api.products.models.item_group import ItemGroup
from api.products.models.item_photo import ItemPhoto
from api.products.models.item_type import ItemType
from api.products.models.like import Like
from api.products.routers.feed import get_photos_by_item_batch
from api.products.schemas.item import CatalogPageResponse, FeedItemResponse, ItemPhotoResponse, LikesSummaryResponse
from api.products.utils.feed_like_counts import get_feed_like_dislike_counts_map, like_dislike_for
from api.products.utils.finance_context import FinancePriceContext, get_finance_price_context
from api.products.utils.customer_price_context import finance_ctx_with_owner_display
from api.products.utils.item_pricing import compute_item_unit_price_for_ctx
from api.products.utils.likes_cache import (
    get_cached_like_item_ids,
    get_cached_summary_total,
    get_likes_revision,
    set_cached_like_item_ids,
    set_cached_summary_total,
)
from api.products.utils.promo_apply import batch_system_photo_promo_badges
from api.products.utils.search import get_search_patterns, text_fuzzy_matches, text_matches_any_pattern
from api.shared.auth import get_user_id_for_request

logger = logging.getLogger(__name__)

router = APIRouter()


async def calculate_item_price(item: Item, ctx: FinancePriceContext) -> Decimal:
    return compute_item_unit_price_for_ctx(item, ctx)


def _item_matches_filters(
    price_rub: Decimal,
    is_legit_item: Optional[bool],
    name: Optional[str],
    description: Optional[str],
    tags: Optional[list],
    price_min: Optional[float],
    price_max: Optional[float],
    is_legit: Optional[bool],
    q: Optional[str],
) -> bool:
    """Проверка одного товара по фильтрам цены, is_legit и поиску q (name, description, tags)."""
    if price_min is not None and float(price_rub) < price_min:
        return False
    if price_max is not None and float(price_rub) > price_max:
        return False
    if is_legit is not None and is_legit_item != is_legit:
        return False
    if q and q.strip():
        patterns = get_search_patterns(q)
        if not patterns:
            patterns = [q.strip()]
        name_ok = text_matches_any_pattern(name or "", patterns) or text_fuzzy_matches(q, name or "")
        desc_ok = text_matches_any_pattern(description or "", patterns) or text_fuzzy_matches(q, description or "")
        tags_list = tags if isinstance(tags, list) else []
        tags_ok = any(
            text_matches_any_pattern(str(tag), patterns) or text_fuzzy_matches(q, str(tag))
            for tag in tags_list
        ) or any(
            text_matches_any_pattern(q, [str(tag)]) or text_matches_any_pattern(str(tag), [q.strip()])
            for tag in tags_list
        )
        if not name_ok and not desc_ok and not tags_ok:
            return False
    return True


def _like_where(user_id: int, action: str) -> Tuple[list, Optional[datetime]]:
    """Условия WHERE для likes; для dislike — нижняя граница по времени."""
    conditions = [Like.user_id == user_id, Like.action == action]
    dislike_since: Optional[datetime] = None
    if action == "dislike":
        dislike_since = datetime.now(timezone.utc) - timedelta(hours=24)
        conditions.append(Like.created_at >= dislike_since)
    return conditions, dislike_since


def _item_passes_type_filters(
    item: Item,
    item_type: Optional[str],
    item_type_id: Optional[List[int]],
) -> bool:
    if item_type_id is not None and len(item_type_id) > 0:
        return item.item_type_id in item_type_id
    if item_type:
        decoded_item_type = unquote(item_type)
        try:
            if isinstance(decoded_item_type, str) and decoded_item_type.strip().isdigit():
                type_id = int(decoded_item_type.strip())
                return bool(item.item_type_rel and item.item_type_rel.id == type_id)
            return bool(item.item_type_rel and item.item_type_rel.name == decoded_item_type)
        except (ValueError, OverflowError):
            return bool(item.item_type_rel and item.item_type_rel.name == decoded_item_type)
    return True


def _has_item_filters(
    item_type: Optional[str],
    item_type_id: Optional[List[int]],
    price_min: Optional[float],
    price_max: Optional[float],
    is_legit: Optional[bool],
    q: Optional[str],
) -> bool:
    if item_type_id is not None and len(item_type_id) > 0:
        return True
    if item_type:
        return True
    if price_min is not None or price_max is not None:
        return True
    if is_legit is not None:
        return True
    if q and str(q).strip():
        return True
    return False


async def _fetch_ordered_like_item_ids(session: AsyncSession, user_id: int, action: str) -> List[int]:
    conditions, _ = _like_where(user_id, action)
    r = await session.execute(
        select(Like.item_id).where(and_(*conditions)).order_by(Like.id.desc()),
    )
    return [int(x[0]) for x in r.all() if x[0] is not None]


async def _fetch_likes_joined_ordered(session: AsyncSession, user_id: int, action: str) -> List[Like]:
    conditions, _ = _like_where(user_id, action)
    stmt = (
        select(Like)
        .join(Item, Like.item_id == Item.id)
        .options(joinedload(Like.item).joinedload(Item.item_type_rel))
        .where(and_(*conditions))
        .order_by(Like.id.desc())
    )
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())


async def collect_filtered_liked_items(
    session: AsyncSession,
    user_id: int,
    action: str,
    ctx: FinancePriceContext,
    item_type: Optional[str],
    item_type_id: Optional[List[int]],
    price_min: Optional[float],
    price_max: Optional[float],
    is_legit: Optional[bool],
    q: Optional[str],
) -> List[Item]:
    likes_rows = await _fetch_likes_joined_ordered(session, user_id, action)
    out: List[Item] = []
    for like in likes_rows:
        item = like.item
        if item is None:
            continue
        if not _item_passes_type_filters(item, item_type, item_type_id):
            continue
        price_rub = await calculate_item_price(item, ctx)
        if not _item_matches_filters(
            price_rub,
            item.is_legit,
            item.name,
            item.description,
            getattr(item, "tags", None),
            price_min,
            price_max,
            is_legit,
            q,
        ):
            continue
        out.append(item)
    return out


async def build_feed_items_batch(
    session: AsyncSession,
    items: List[Item],
    ctx: FinancePriceContext,
) -> List[FeedItemResponse]:
    if not items:
        return []
    item_ids = [i.id for i in items]
    photos_by_item = await get_photos_by_item_batch(session, item_ids)
    group_ids = list({i.group_id for i in items if i.group_id})
    group_names: dict[int, str] = {}
    if group_ids:
        gr = await session.execute(select(ItemGroup.id, ItemGroup.name).where(ItemGroup.id.in_(group_ids)))
        group_names = {int(r[0]): str(r[1]) for r in gr.all() if r[0] is not None}
    promo_badges = await batch_system_photo_promo_badges(session, item_ids)
    counts_map = await get_feed_like_dislike_counts_map(session, item_ids)
    out: List[FeedItemResponse] = []
    for item in items:
        photos = photos_by_item.get(item.id) or []
        price_rub = await calculate_item_price(item, ctx)
        telegram_file_id = photos[0].telegram_file_id if photos else None
        vk_attachment = photos[0].vk_attachment if photos else None
        size_str = None
        if item.size:
            if isinstance(item.size, list):
                size_str = ", ".join(str(s) for s in item.size)
            else:
                size_str = str(item.size)
        group_id = item.group_id
        group_name = group_names.get(group_id) if group_id else None
        lc, dc = like_dislike_for(counts_map, item.id)
        out.append(
            FeedItemResponse(
                id=item.id,
                name=item.name,
                description=item.description,
                item_type=item.item_type_rel.name if item.item_type_rel else None,
                item_type_id=item.item_type_id,
                price_rub=price_rub,
                size=size_str,
                min_price_week=None,
                max_price_week=None,
                telegram_file_id=telegram_file_id,
                vk_attachment=vk_attachment,
                photos=[
                    ItemPhotoResponse(
                        id=photo.id,
                        file_path=photo.file_path,
                        telegram_file_id=photo.telegram_file_id,
                        vk_attachment=photo.vk_attachment,
                        sort_order=getattr(photo, "sort_order", 0),
                    )
                    for photo in photos
                ],
                group_id=group_id,
                group_name=group_name,
                group_items=[],
                is_group=False,
                is_legit=item.is_legit,
                photo_promo_badge=promo_badges.get(item.id),
                feed_like_count=lc,
                feed_dislike_count=dc,
            )
        )
    return out


async def _load_items_preserve_order(session: AsyncSession, ids: List[int]) -> List[Item]:
    if not ids:
        return []
    result = await session.execute(
        select(Item).options(joinedload(Item.item_type_rel)).where(Item.id.in_(ids)),
    )
    by_id = {int(i.id): i for i in result.unique().scalars().all()}
    return [by_id[i] for i in ids if i in by_id]


async def get_liked_page_core(
    session: AsyncSession,
    user_id: int,
    action: str,
    platform: str,
    offset: int,
    limit: int,
    item_type: Optional[str],
    item_type_id: Optional[List[int]],
    price_min: Optional[float],
    price_max: Optional[float],
    is_legit: Optional[bool],
    q: Optional[str],
    authorization: Optional[str] = None,
) -> CatalogPageResponse:
    ctx = await finance_ctx_with_owner_display(await get_finance_price_context(), authorization)
    pf = platform or "tg"
    rev = await get_likes_revision(pf, user_id, action)
    filters_on = _has_item_filters(item_type, item_type_id, price_min, price_max, is_legit, q)

    if not filters_on:
        ordered_ids = await get_cached_like_item_ids(pf, user_id, action, rev)
        if ordered_ids is None:
            ordered_ids = await _fetch_ordered_like_item_ids(session, user_id, action)
            await set_cached_like_item_ids(pf, user_id, action, rev, ordered_ids)
        total = len(ordered_ids)
        window_ids = ordered_ids[offset : offset + limit]
        page_items = await _load_items_preserve_order(session, window_ids)
        items_out = await build_feed_items_batch(session, page_items, ctx)
        has_more = offset + limit < total
        return CatalogPageResponse(
            items=items_out,
            total=total,
            has_more=has_more,
            next_offset=(offset + limit) if has_more else None,
        )

    filtered = await collect_filtered_liked_items(
        session, user_id, action, ctx, item_type, item_type_id, price_min, price_max, is_legit, q
    )
    total = len(filtered)
    page_items = filtered[offset : offset + limit]
    items_out = await build_feed_items_batch(session, page_items, ctx)
    has_more = offset + limit < total
    return CatalogPageResponse(
        items=items_out,
        total=total,
        has_more=has_more,
        next_offset=(offset + limit) if has_more else None,
    )


@router.get("/likes/summary", response_model=LikesSummaryResponse)
async def get_likes_summary(
    action: str = Query("like", description="like, dislike или save"),
    known_rev: Optional[int] = Query(None, description="Ревизия с прошлого ответа — если совпадает, можно отдать count из кеша без COUNT в БД"),
    platform: Optional[str] = Header(None, alias="X-Platform"),
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """
    Число записей на полке (без фильтров каталога) + ревизия для кеша.
    При совпадении known_rev с текущей ревизией ответ берётся из Redis (без запроса COUNT в PostgreSQL).
    """
    if action not in ("like", "dislike", "save"):
        raise HTTPException(status_code=400, detail="Неподдерживаемое действие")
    pf = platform or "tg"
    rev = await get_likes_revision(pf, user_id, action)
    if known_rev is not None and int(known_rev) == rev:
        cached = await get_cached_summary_total(pf, user_id, action, rev)
        if cached is not None:
            return LikesSummaryResponse(total=cached, rev=rev)
    conditions, _ = _like_where(user_id, action)
    cnt_result = await session.execute(select(func.count(Like.id)).where(and_(*conditions)))
    total = int(cnt_result.scalar() or 0)
    await set_cached_summary_total(pf, user_id, action, rev, total)
    return LikesSummaryResponse(total=total, rev=rev)


@router.get("/likes/page", response_model=CatalogPageResponse)
async def get_liked_items_page(
    action: str = Query(..., description="like, dislike или save"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    item_type: Optional[str] = Query(None, description="Фильтр по типу товара (название или ID)"),
    item_type_id: Optional[List[int]] = Query(None, description="Фильтр по типам товара (несколько ID)"),
    price_min: Optional[float] = Query(None, description="Минимальная цена (руб)"),
    price_max: Optional[float] = Query(None, description="Максимальная цена (руб)"),
    is_legit: Optional[bool] = Query(None, description="Оригинал (True) или реплика (False)"),
    q: Optional[str] = Query(None, description="Поиск по названию и описанию"),
    platform: Optional[str] = Header(None, alias="X-Platform"),
    authorization: Optional[str] = Header(None),
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """Понравившиеся пачками (как каталог): items, total, has_more, next_offset."""
    if action not in ("like", "dislike", "save"):
        raise HTTPException(status_code=400, detail="Неподдерживаемое действие")
    return await get_liked_page_core(
        session,
        user_id,
        action,
        platform or "tg",
        offset,
        limit,
        item_type,
        item_type_id,
        price_min,
        price_max,
        is_legit,
        q,
        authorization,
    )


@router.get("/likes", response_model=List[FeedItemResponse])
async def get_liked_items(
    action: str = Query(..., description="like, dislike или save"),
    item_type: Optional[str] = Query(None, description="Фильтр по типу товара (название или ID)"),
    item_type_id: Optional[List[int]] = Query(None, description="Фильтр по типам товара (несколько ID)"),
    price_min: Optional[float] = Query(None, description="Минимальная цена (руб)"),
    price_max: Optional[float] = Query(None, description="Максимальная цена (руб)"),
    is_legit: Optional[bool] = Query(None, description="Оригинал (True) или реплика (False)"),
    q: Optional[str] = Query(None, description="Поиск по названию и описанию"),
    platform: Optional[str] = Header(None, alias="X-Platform"),
    authorization: Optional[str] = Header(None),
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """Совместимость: полный список (боты). Мини-апп лучше использовать /likes/page и /likes/summary."""
    if action not in ("like", "dislike", "save"):
        raise HTTPException(status_code=400, detail="Неподдерживаемое действие")
    page = await get_liked_page_core(
        session,
        user_id,
        action,
        platform or "tg",
        0,
        10000,
        item_type,
        item_type_id,
        price_min,
        price_max,
        is_legit,
        q,
        authorization,
    )
    return page.items


@router.get("/likes/types")
async def get_liked_item_types(
    action: str = Query(..., description="like, dislike или save"),
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """Получить список типов товаров, у которых есть лайки/дизлайки/сохраненные"""
    if action not in ("like", "dislike", "save"):
        raise HTTPException(status_code=400, detail="Неподдерживаемое действие")

    result = await session.execute(
        select(ItemType.name)
        .join(Item, ItemType.id == Item.item_type_id)
        .join(Like, Item.id == Like.item_id)
        .where(
            and_(
                Like.user_id == user_id,
                Like.action == action,
            ),
        )
        .distinct(),
    )

    types = [row[0] for row in result.all()]
    return {"types": types}
