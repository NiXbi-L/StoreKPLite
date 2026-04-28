"""
Роутер для ленты товаров
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, not_, func, or_, text, case
from typing import Optional
from decimal import Decimal
import logging

from api.products.database import database as db_module
from api.products.database.database import get_session
from api.products.models.item import Item
from api.products.models.item_photo import ItemPhoto
from api.products.models.like import Like
from api.products.models.item_price_history import ItemPriceHistory
from api.products.models.item_group import ItemGroup
from api.products.models.item_stock import ItemStock
from api.products.schemas.item import FeedItemResponse, ItemPhotoResponse, CatalogPageResponse, ItemGroupByItemResponse
from api.shared.auth import get_user_id_for_request
from datetime import timedelta
from api.shared.timezone import now_vladivostok
from api.products.utils.finance_context import get_finance_price_context, FinancePriceContext
from api.products.utils.customer_price_context import finance_ctx_with_owner_display
from api.products.utils.item_pricing import compute_item_unit_price_for_ctx
from api.products.utils.promo_apply import batch_system_photo_promo_badges
from api.products.utils.feed_like_counts import get_feed_like_dislike_counts_map, like_dislike_for
from os import getenv
import hashlib
import json
import time

logger = logging.getLogger(__name__)

router = APIRouter()

REDIS_URL = getenv("REDIS_URL", "redis://products-redis:6379/0")


async def invalidate_catalog_cache() -> None:
    """Удалить все ключи кеша каталога (catalog:search:*). Вызывать при создании/изменении/удалении товаров."""
    try:
        import redis.asyncio as redis
        client = await redis.from_url(REDIS_URL, decode_responses=True)
        keys = []
        async for key in client.scan_iter(match="catalog:search:*"):
            keys.append(key)
        if keys:
            await client.delete(*keys)
        await client.close()
    except Exception as e:
        logger.debug("Catalog cache invalidation skip: %s", e)


# Кеш: полный price-context от finance, TTL 60 сек
_price_context_cache: tuple[float, Optional[FinancePriceContext]] = (0.0, None)
_CACHE_TTL = 60.0


async def get_cached_price_context() -> FinancePriceContext:
    """Курс, доставка и коэффициенты цены (кеш 60 сек)."""
    global _price_context_cache
    now = time.monotonic()
    if (
        _price_context_cache[1] is not None
        and now - _price_context_cache[0] < _CACHE_TTL
    ):
        return _price_context_cache[1]
    ctx = await get_finance_price_context()
    _price_context_cache = (now, ctx)
    return ctx


async def calculate_item_price(
    item: Item,
    ctx: Optional[FinancePriceContext] = None,
) -> Decimal:
    """
    StoreKPLite: упрощённая модель цены — только фиксированная цена в рублях.
    Если fixed_price не задан, используем поле price как рублёвую цену.
    """
    fixed = getattr(item, "fixed_price", None)
    if fixed is not None:
        return Decimal(str(fixed)).quantize(Decimal("0.01"))
    return Decimal(str(item.price)).quantize(Decimal("0.01"))




async def get_item_ids_with_stock(session: AsyncSession, item_ids: list[int]) -> set[int]:
    """Возвращает множество item_id, у которых есть хотя бы один размер с quantity > 0."""
    if not item_ids:
        return set()
    result = await session.execute(
        select(ItemStock.item_id).where(
            and_(ItemStock.item_id.in_(item_ids), ItemStock.quantity > 0)
        ).distinct()
    )
    return {row[0] for row in result.all()}


async def get_price_history(item_id: int, session: AsyncSession) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Мин/макс цена за последние 7 дней (по всем 4h-срезам)."""
    cutoff = now_vladivostok() - timedelta(days=7)
    result = await session.execute(
        select(
            func.min(ItemPriceHistory.min_price),
            func.max(ItemPriceHistory.max_price),
        ).where(
            ItemPriceHistory.item_id == item_id,
            ItemPriceHistory.week_start >= cutoff,
        )
    )
    row = result.one_or_none()
    if row and row[0] is not None and row[1] is not None:
        return row[0], row[1]
    return None, None


async def get_price_history_batch(
    session: AsyncSession, item_ids: list[int]
) -> dict[int, tuple[Optional[Decimal], Optional[Decimal]]]:
    """Мин/макс цена за 7 дней для списка товаров одним запросом."""
    if not item_ids:
        return {}
    cutoff = now_vladivostok() - timedelta(days=7)
    result = await session.execute(
        select(
            ItemPriceHistory.item_id,
            func.min(ItemPriceHistory.min_price),
            func.max(ItemPriceHistory.max_price),
        )
        .where(
            ItemPriceHistory.item_id.in_(item_ids),
            ItemPriceHistory.week_start >= cutoff,
        )
        .group_by(ItemPriceHistory.item_id)
    )
    return {
        row[0]: (row[1], row[2])
        for row in result.all()
        if row[1] is not None and row[2] is not None
    }


async def get_photos_by_item_batch(
    session: AsyncSession, item_ids: list[int]
) -> dict[int, list]:
    """Все фото по списку item_id одним запросом, сгруппированные по item_id (порядок по sort_order, id)."""
    if not item_ids:
        return {}
    result = await session.execute(
        select(ItemPhoto)
        .where(ItemPhoto.item_id.in_(item_ids))
        .order_by(
            ItemPhoto.item_id,
            func.coalesce(ItemPhoto.sort_order, 999999).asc(),
            ItemPhoto.id,
        )
    )
    photos = result.scalars().all()
    by_item: dict[int, list] = {i: [] for i in item_ids}
    for p in photos:
        by_item.setdefault(p.item_id, []).append(p)
    return by_item


@router.get("/feed/catalog", response_model=CatalogPageResponse)
async def get_catalog_page(
    limit: int = 20,
    offset: int = 0,
    q: Optional[str] = Query(None, description="Поиск по названию / описанию"),
    item_type_id: Optional[list[int]] = Query(
        None, description="Фильтр по типу товара (один или несколько ID)"
    ),
    price_min: Optional[float] = Query(None, description="Минимальная цена (руб)"),
    price_max: Optional[float] = Query(None, description="Максимальная цена (руб)"),
    is_legit: Optional[bool] = Query(
        None, description="Фильтр по типу товара: оригинал (True) или реплика (False)"
    ),
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    platform_id: Optional[str] = Header(None, alias="X-Platform-Id"),
    platform: Optional[str] = Header(None, alias="X-Platform"),
    session: AsyncSession = Depends(get_session),
):
    """
    Пагинированный каталог для мини-аппа: пачки карточек товаров.
    Параметры: limit, offset, q (поиск), item_type_id (может повторяться несколько раз),
    price_min, price_max.
    Возвращает: items, total, has_more, next_offset.
    """
    # Опционально определяем user_id (если есть токен); ошибки авторизации не ломают публичный доступ
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

    if limit < 1 or limit > 50:
        limit = 20
    if offset < 0:
        offset = 0

    q_clean = (q or "").strip()
    ctx = await finance_ctx_with_owner_display(await get_cached_price_context(), authorization)

    # Нормализация фильтров для ключа кеша (запрос + фильтры)
    def _catalog_cache_key() -> str:
        q_norm = (q or "").strip().lower()
        type_norm = sorted(item_type_id) if item_type_id else []
        legit_norm = "" if is_legit is None else ("1" if is_legit else "0")
        parts = [q_norm, ",".join(str(x) for x in type_norm), legit_norm]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    # Кеш только когда нет фильтра по цене (результат не зависит от курса)
    use_cache = price_min is None and price_max is None
    cache_key_redis = f"catalog:search:v5:{_catalog_cache_key()}" if use_cache else None

    if use_cache and cache_key_redis:
        try:
            import redis.asyncio as redis
            redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
            cached = await redis_client.get(cache_key_redis)
            await redis_client.close()
            if cached:
                data = json.loads(cached)
                item_ids_all = data.get("item_ids") or []
                total_cached = data.get("total") or 0
                page_ids = item_ids_all[offset : offset + limit]
                if page_ids:
                    order_case = case({id_: i for i, id_ in enumerate(page_ids)}, value=Item.id)
                    result = await session.execute(
                        select(Item).where(Item.id.in_(page_ids)).order_by(order_case)
                    )
                    items_slice = result.scalars().all()
                else:
                    items_slice = []
                total = total_cached
                has_more = total > offset + limit
                next_offset = (offset + limit) if has_more else None
                item_ids_page = [item.id for item in items_slice]
                items_with_stock = await get_item_ids_with_stock(session, item_ids_page)
                price_hist = await get_price_history_batch(session, item_ids_page)
                photos_by_item = await get_photos_by_item_batch(session, item_ids_page)
                promo_badges = await batch_system_photo_promo_badges(session, item_ids_page)
                counts_map = await get_feed_like_dislike_counts_map(session, item_ids_page)
                liked_ids = set()
                if user_id and items_slice:
                    from api.products.models.like import Like
                    liked_result = await session.execute(
                        select(Like.item_id).where(
                            and_(
                                Like.user_id == user_id,
                                Like.action == "like",
                                Like.item_id.in_(item_ids_page),
                            )
                        )
                    )
                    liked_ids = {row[0] for row in liked_result.all()}
                out = []
                for item in items_slice:
                    price_rub = await calculate_item_price(item, ctx)
                    min_price, max_price = price_hist.get(item.id, (None, None)) or (price_rub, price_rub)
                    photos = photos_by_item.get(item.id, [])
                    size_str = ", ".join(map(str, item.size)) if isinstance(item.size, list) else (str(item.size) if item.size else None)
                    fixed_price_rub = getattr(item, "fixed_price", None) if item.id in items_with_stock else None
                    lc, dc = like_dislike_for(counts_map, item.id)
                    out.append(
                        FeedItemResponse(
                            id=item.id,
                            name=item.name,
                            description=item.description,
                            price_rub=price_rub,
                            size=size_str,
                            min_price_week=min_price,
                            max_price_week=max_price,
                            telegram_file_id=photos[0].telegram_file_id if photos else None,
                            vk_attachment=photos[0].vk_attachment if photos else None,
                            photos=[ItemPhotoResponse(id=p.id, file_path=p.file_path, telegram_file_id=p.telegram_file_id, vk_attachment=p.vk_attachment, sort_order=getattr(p, "sort_order", 0)) for p in photos],
                            group_id=item.group_id,
                            group_name=None,
                            group_items=[],
                            is_group=False,
                            is_legit=getattr(item, "is_legit", None),
                            liked=item.id in liked_ids if user_id else None,
                            fixed_price_rub=fixed_price_rub,
                            photo_promo_badge=promo_badges.get(item.id),
                            feed_like_count=lc,
                            feed_dislike_count=dc,
                        )
                    )
                return CatalogPageResponse(items=out, total=total, has_more=has_more, next_offset=next_offset)
        except Exception as e:
            logger.debug("Catalog cache read skip: %s", e)

    # Базовый запрос по товарам
    items_query = select(Item)
    if q_clean:
        # Поиск: подстрока (ILIKE); если установлен pg_trgm — ещё триграммная похожесть (опечатки)
        pattern = f"%{q_clean}%"
        # tags может быть не массивом (скаляр/null) — оборачиваем в безопасный массив
        tags_array_safe = "jsonb_array_elements_text(CASE WHEN jsonb_typeof(items.tags) = 'array' THEN items.tags ELSE '[]'::jsonb END)"
        search_conditions = [
            Item.name.ilike(pattern),
            Item.description.ilike(pattern),
            text(
                f"EXISTS (SELECT 1 FROM {tags_array_safe} t WHERE t ILIKE :pat OR :q_sub ILIKE '%' || t || '%')"
            ).bindparams(pat=pattern, q_sub=q_clean),
        ]
        if db_module.PG_TRGM_AVAILABLE:
            trgm_thresh = 0.18
            search_conditions.extend([
                text(
                    f"EXISTS (SELECT 1 FROM {tags_array_safe} t WHERE similarity(lower(t)::text, lower(:q_trgm)::text) > :trgm_thresh OR word_similarity(lower(:q_trgm)::text, lower(t)::text) > :trgm_thresh)"
                ).bindparams(q_trgm=q_clean, trgm_thresh=trgm_thresh),
                text(
                    f"similarity(lower(COALESCE((SELECT string_agg(t, ' ') FROM {tags_array_safe} t), ''))::text, lower(:q_trgm)::text) > :trgm_thresh"
                ).bindparams(q_trgm=q_clean, trgm_thresh=trgm_thresh),
                text(
                    "similarity(lower(items.name)::text, lower(:q_trgm)::text) > :trgm_thresh OR word_similarity(lower(:q_trgm)::text, lower(items.name)::text) > :trgm_thresh"
                ).bindparams(q_trgm=q_clean, trgm_thresh=trgm_thresh),
            ])
        items_query = items_query.where(or_(*search_conditions))
    if item_type_id:
        items_query = items_query.where(Item.item_type_id.in_(item_type_id))
    if is_legit is not None:
        items_query = items_query.where(Item.is_legit == is_legit)

    # Сортировка по релевантности: название + теги (чтобы «кулон» в тегах поднимал товар выше)
    if q_clean and db_module.PG_TRGM_AVAILABLE:
        tags_array_safe_order = "jsonb_array_elements_text(CASE WHEN jsonb_typeof(items.tags) = 'array' THEN items.tags ELSE '[]'::jsonb END)"
        items_query = items_query.order_by(
            text(
                "greatest("
                " coalesce(similarity(lower(items.name)::text, lower(:q_trgm)::text), 0),"
                " coalesce(word_similarity(lower(:q_trgm)::text, lower(items.name)::text), 0),"
                f" coalesce((SELECT max(similarity(lower(t)::text, lower(:q_trgm)::text)) FROM {tags_array_safe_order} t), 0),"
                f" coalesce((SELECT max(word_similarity(lower(:q_trgm)::text, lower(t)::text)) FROM {tags_array_safe_order} t), 0)"
                ") DESC NULLS LAST"
            ).bindparams(q_trgm=q_clean)
        )
    else:
        items_query = items_query.order_by(Item.id.desc())

    use_price_filter = price_min is not None or price_max is not None

    if use_price_filter:
        # Фильтр по цене: получаем все подходящие товары, считаем цену, фильтруем, пагинируем в памяти
        result = await session.execute(items_query)
        all_rows = result.scalars().all()
        out_with_price = []
        for item in all_rows:
            price_rub = await calculate_item_price(item, ctx)
            if price_min is not None and float(price_rub) < price_min:
                continue
            if price_max is not None and float(price_rub) > price_max:
                continue
            out_with_price.append((item, price_rub))
        total = len(out_with_price)
        if not q_clean:
            out_with_price.sort(key=lambda x: -x[0].id)
        page_slice = out_with_price[offset : offset + limit]
        has_more = total > offset + limit
        next_offset = (offset + limit) if has_more else None
        item_ids_page = [item.id for item, _ in page_slice]
        items_with_stock = await get_item_ids_with_stock(session, item_ids_page)
        price_hist = await get_price_history_batch(session, item_ids_page)
        photos_by_item = await get_photos_by_item_batch(session, item_ids_page)
        promo_badges = await batch_system_photo_promo_badges(session, item_ids_page)
        counts_map = await get_feed_like_dislike_counts_map(session, item_ids_page)
        out = []
        liked_ids: set[int] = set()
        if user_id is not None and page_slice:
            from api.products.models.like import Like
            from sqlalchemy import and_
            liked_result = await session.execute(
                select(Like.item_id).where(
                    and_(
                        Like.user_id == user_id,
                        Like.action == "like",
                        Like.item_id.in_(item_ids_page),
                    )
                )
            )
            liked_ids = {row[0] for row in liked_result.all()}
        for item, price_rub in page_slice:
            min_price, max_price = price_hist.get(item.id, (None, None))
            if min_price is None:
                min_price = price_rub
            if max_price is None:
                max_price = price_rub
            photos = photos_by_item.get(item.id, [])
            photos_list = [
                ItemPhotoResponse(
                    id=p.id,
                    file_path=p.file_path,
                    telegram_file_id=p.telegram_file_id,
                    vk_attachment=p.vk_attachment,
                    sort_order=getattr(p, "sort_order", 0),
                )
                for p in photos
            ]
            telegram_file_id = photos[0].telegram_file_id if photos else None
            vk_attachment = photos[0].vk_attachment if photos else None
            size_str = None
            if item.size:
                size_str = ", ".join(str(s) for s in item.size) if isinstance(item.size, list) else str(item.size)
            fixed_price_rub = (getattr(item, "fixed_price", None) if item.id in items_with_stock else None)
            lc, dc = like_dislike_for(counts_map, item.id)
            out.append(
                FeedItemResponse(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    price_rub=price_rub,
                    size=size_str,
                    min_price_week=min_price,
                    max_price_week=max_price,
                    telegram_file_id=telegram_file_id,
                    vk_attachment=vk_attachment,
                    photos=photos_list,
                    group_id=item.group_id,
                    group_name=None,
                    group_items=[],
                    is_group=False,
                    is_legit=getattr(item, "is_legit", None),
                    liked=item.id in liked_ids if user_id is not None else None,
                    fixed_price_rub=fixed_price_rub,
                    photo_promo_badge=promo_badges.get(item.id),
                    feed_like_count=lc,
                    feed_dislike_count=dc,
                )
            )
        return CatalogPageResponse(
            items=out,
            total=total,
            has_more=has_more,
            next_offset=next_offset,
        )

    # Без фильтра по цене: пагинация в БД (или из кеша уже отдано выше)
    count_result = await session.execute(
        select(func.count()).select_from(items_query.subquery())
    )
    total = count_result.scalar() or 0

    items_slice = []
    if use_cache and cache_key_redis and total > 0 and total <= 2000:
        # Один полный запрос: кешируем id и сразу берём срез для ответа
        full_result = await session.execute(items_query)
        all_rows = full_result.scalars().all()
        all_ids = [r.id for r in all_rows]
        try:
            import redis.asyncio as redis
            rclient = await redis.from_url(REDIS_URL, decode_responses=True)
            await rclient.setex(
                cache_key_redis,
                86400,  # 24 ч
                json.dumps({"item_ids": all_ids, "total": total}),
            )
            await rclient.close()
        except Exception as e:
            logger.debug("Catalog cache write skip: %s", e)
        items_slice = all_rows[offset : offset + limit]
        has_more = total > offset + limit
        next_offset = (offset + limit) if has_more else None
    else:
        paged_query = items_query.offset(offset).limit(limit + 1)
        result = await session.execute(paged_query)
        rows = result.scalars().all()
        has_more = len(rows) > limit
        items_slice = rows[:limit]
        next_offset = (offset + limit) if has_more else None

    item_ids_page = [item.id for item in items_slice]
    items_with_stock = await get_item_ids_with_stock(session, item_ids_page)
    price_hist = await get_price_history_batch(session, item_ids_page)
    photos_by_item = await get_photos_by_item_batch(session, item_ids_page)
    promo_badges = await batch_system_photo_promo_badges(session, item_ids_page)
    counts_map = await get_feed_like_dislike_counts_map(session, item_ids_page)

    out = []
    liked_ids: set[int] = set()
    if user_id is not None and items_slice:
        from api.products.models.like import Like
        from sqlalchemy import and_
        liked_result = await session.execute(
            select(Like.item_id).where(
                and_(
                    Like.user_id == user_id,
                    Like.action == "like",
                    Like.item_id.in_(item_ids_page),
                )
            )
        )
        liked_ids = {row[0] for row in liked_result.all()}

    for item in items_slice:
        price_rub = await calculate_item_price(item, ctx)
        min_price, max_price = price_hist.get(item.id, (None, None))
        if min_price is None:
            min_price = price_rub
        if max_price is None:
            max_price = price_rub
        photos = photos_by_item.get(item.id, [])
        photos_list = [
            ItemPhotoResponse(
                id=p.id,
                file_path=p.file_path,
                telegram_file_id=p.telegram_file_id,
                vk_attachment=p.vk_attachment,
                sort_order=getattr(p, "sort_order", 0),
            )
            for p in photos
        ]
        telegram_file_id = photos[0].telegram_file_id if photos else None
        vk_attachment = photos[0].vk_attachment if photos else None
        size_str = None
        if item.size:
            size_str = ", ".join(str(s) for s in item.size) if isinstance(item.size, list) else str(item.size)
        fixed_price_rub = (getattr(item, "fixed_price", None) if item.id in items_with_stock else None)
        lc, dc = like_dislike_for(counts_map, item.id)
        out.append(
            FeedItemResponse(
                id=item.id,
                name=item.name,
                description=item.description,
                price_rub=price_rub,
                size=size_str,
                min_price_week=min_price,
                max_price_week=max_price,
                telegram_file_id=telegram_file_id,
                vk_attachment=vk_attachment,
                photos=photos_list,
                group_id=item.group_id,
                group_name=None,
                group_items=[],
                is_group=False,
                is_legit=item.is_legit,
                liked=item.id in liked_ids if user_id is not None else None,
                fixed_price_rub=fixed_price_rub,
                photo_promo_badge=promo_badges.get(item.id),
                feed_like_count=lc,
                feed_dislike_count=dc,
            )
        )

    return CatalogPageResponse(
        items=out,
        total=total,
        has_more=has_more,
        next_offset=next_offset,
    )


@router.get("/feed/items/{item_id}/group", response_model=ItemGroupByItemResponse)
async def get_item_group(
    item_id: int,
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Карточки группы по конкретной вещи.
    Если вещь в группе — возвращает группу (group_id, group_name, items — все карточки группы).
    Если вещь не в группе или связей нет — in_group=False, items=[].
    """
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")

    if not item.group_id:
        return ItemGroupByItemResponse(in_group=False, group_id=None, group_name=None, items=[])

    group_result = await session.execute(select(ItemGroup).where(ItemGroup.id == item.group_id))
    group = group_result.scalar_one_or_none()
    if not group:
        return ItemGroupByItemResponse(in_group=False, group_id=None, group_name=None, items=[])

    ctx = await finance_ctx_with_owner_display(await get_cached_price_context(), authorization)

    group_items_result = await session.execute(
        select(Item).where(Item.group_id == item.group_id).order_by(Item.id)
    )
    group_items = group_items_result.scalars().all()
    group_ids = [g.id for g in group_items]
    price_hist = await get_price_history_batch(session, group_ids)
    photos_by_item = await get_photos_by_item_batch(session, group_ids)
    promo_badges = await batch_system_photo_promo_badges(session, group_ids)
    counts_map = await get_feed_like_dislike_counts_map(session, group_ids)
    out = []
    for group_item in group_items:
        price_rub = await calculate_item_price(group_item, ctx)
        min_price, max_price = price_hist.get(group_item.id, (None, None))
        if min_price is None:
            min_price = price_rub
        if max_price is None:
            max_price = price_rub
        photos = photos_by_item.get(group_item.id, [])
        photos_list = [
            ItemPhotoResponse(
                id=p.id,
                file_path=p.file_path,
                telegram_file_id=p.telegram_file_id,
                vk_attachment=p.vk_attachment,
                sort_order=getattr(p, "sort_order", 0),
            )
            for p in photos
        ]
        telegram_file_id = photos[0].telegram_file_id if photos else None
        vk_attachment = photos[0].vk_attachment if photos else None
        size_str = None
        if group_item.size:
            size_str = ", ".join(str(s) for s in group_item.size) if isinstance(group_item.size, list) else str(group_item.size)
        lc, dc = like_dislike_for(counts_map, group_item.id)
        out.append(
            FeedItemResponse(
                id=group_item.id,
                name=group_item.name,
                description=group_item.description,
                price_rub=price_rub,
                size=size_str,
                min_price_week=min_price,
                max_price_week=max_price,
                telegram_file_id=telegram_file_id,
                vk_attachment=vk_attachment,
                photos=photos_list,
                group_id=group.id,
                group_name=group.name,
                group_items=[],
                is_group=False,
                is_legit=group_item.is_legit,
                photo_promo_badge=promo_badges.get(group_item.id),
                feed_like_count=lc,
                feed_dislike_count=dc,
            )
        )

    return ItemGroupByItemResponse(
        in_group=True,
        group_id=group.id,
        group_name=group.name,
        items=out,
    )

