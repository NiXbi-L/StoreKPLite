"""
Роутер для работы с товарами
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from api.products.database.database import get_session
from api.products.models.item import Item
from api.products.models.order import Order
from api.products.models.item_photo import ItemPhoto
from api.products.models.item_price_history import ItemPriceHistory
from api.products.models.item_stock import ItemStock
from api.products.models.cart import Cart
from api.products.models.item_type import ItemType
from api.products.schemas.item import ItemResponse, ItemPhotoResponse, FeedItemResponse, InCartEntry
from api.products.schemas.size_chart import SizeChartResponse
from api.shared.timezone import now_vladivostok
from api.shared.auth import get_user_id_for_request
from api.products.utils.finance_context import get_finance_price_context, FinancePriceContext
from api.products.utils.customer_price_context import finance_ctx_with_owner_display
from api.products.utils.item_pricing import compute_item_unit_price_for_ctx
from api.products.utils.promo_apply import batch_system_photo_promo_badges
from api.products.utils.feed_like_counts import get_feed_like_dislike_counts_map, like_dislike_for

logger = logging.getLogger(__name__)

router = APIRouter()

INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")


def check_internal_token(token: Optional[str] = None) -> bool:
    if not token:
        return False
    clean = token.replace("Bearer ", "").strip() if token.startswith("Bearer") else token.strip()
    return clean == INTERNAL_TOKEN


async def calculate_item_price(item: Item, ctx: FinancePriceContext) -> Decimal:
    return compute_item_unit_price_for_ctx(item, ctx)


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


def build_price_history_chart_points(history_rows: List[Any]) -> List[dict]:
    """
    Строит точки для графика: за прошедшие дни — одна точка в день (средняя за день),
    за текущий день — точки по 4 часа (средняя за 4h).
    """
    from api.shared.timezone import VLADIVOSTOK
    today = now_vladivostok().date()
    by_day: dict = defaultdict(list)
    for row in history_rows:
        if not getattr(row, "week_start", None):
            continue
        dt = row.week_start.astimezone(VLADIVOSTOK) if getattr(row.week_start, "astimezone", None) else row.week_start
        day = dt.date() if hasattr(dt, "date") else dt
        avg = getattr(row, "avg_price", None) or (row.min_price + row.max_price) / 2
        by_day[day].append({"week_start": row.week_start, "min_price": row.min_price, "max_price": row.max_price, "avg_price": avg})
    out = []
    for day in sorted(by_day.keys()):
        buckets = by_day[day]
        if day == today:
            for b in sorted(buckets, key=lambda x: x["week_start"]):
                out.append({
                    "week_start": b["week_start"],
                    "min_price": b["min_price"],
                    "max_price": b["max_price"],
                    "avg_price": b["avg_price"],
                })
        else:
            avg_price = sum(b["avg_price"] for b in buckets) / len(buckets)
            min_price = min(b["min_price"] for b in buckets)
            max_price = max(b["max_price"] for b in buckets)
            first_start = min(b["week_start"] for b in buckets)
            out.append({
                "week_start": first_start,
                "min_price": min_price,
                "max_price": max_price,
                "avg_price": avg_price,
            })
    return sorted(out, key=lambda x: x["week_start"])


@router.get("/items/{item_id}", response_model=FeedItemResponse)
async def get_item_by_id(
    item_id: int,
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    platform_id: Optional[str] = Header(None, alias="X-Platform-Id"),
    platform: Optional[str] = Header(None, alias="X-Platform"),
    session: AsyncSession = Depends(get_session),
):
    """
    Получить товар по ID с расчетом цены и историей
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

    # Получаем товар с типом вещи и размерной сеткой
    result = await session.execute(
        select(Item).options(joinedload(Item.item_type_rel), joinedload(Item.size_chart)).where(Item.id == item_id)
    )
    item = result.unique().scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    # Есть ли остаток хотя бы по одному размеру (для fixed_price_rub)
    stock_result = await session.execute(
        select(ItemStock.item_id).where(
            and_(ItemStock.item_id == item.id, ItemStock.quantity > 0)
        ).limit(1)
    )
    has_stock = stock_result.scalar_one_or_none() is not None
    
    # Один запрос к finance: курс и стоимость доставки (владельцу — отображение как при оформлении заказа)
    ctx = await finance_ctx_with_owner_display(await get_finance_price_context(), authorization)

    # Рассчитываем цену
    price_rub = await calculate_item_price(item, ctx)
    
    # Получаем историю цен за текущую неделю
    min_price, max_price = await get_price_history(item.id, session)
    
    # Если истории нет, создаём запись в текущем 4h-окне
    if min_price is None or max_price is None:
        from api.products.routers.price_history import upsert_price_history_4h_bucket
        await upsert_price_history_4h_bucket(session, item.id, price_rub)
        await session.commit()
        min_price = price_rub
        max_price = price_rub
        logger.info(f"Создана история цен для товара {item.id}: min=max={price_rub}")

    # Полная история для графика: прошедшие дни — 1 точка/день (средняя), сегодня — по 4h
    cutoff = now_vladivostok() - timedelta(days=7)
    history_result = await session.execute(
        select(ItemPriceHistory)
        .where(
            ItemPriceHistory.item_id == item.id,
            ItemPriceHistory.week_start >= cutoff,
        )
        .order_by(ItemPriceHistory.week_start.asc())
    )
    history_rows = history_result.scalars().all()
    price_history = build_price_history_chart_points(history_rows)
    
    # Получаем фото
    photos_result = await session.execute(
        select(ItemPhoto).where(ItemPhoto.item_id == item.id).order_by(
            func.coalesce(ItemPhoto.sort_order, 999999).asc(),
            ItemPhoto.id
        )
    )
    photos = photos_result.scalars().all()
    
    # Первое фото для быстрой отправки
    telegram_file_id = photos[0].telegram_file_id if photos else None
    vk_attachment = photos[0].vk_attachment if photos else None
    
    photos_list = [ItemPhotoResponse(
        id=photo.id,
        file_path=photo.file_path,
        telegram_file_id=photo.telegram_file_id,
        vk_attachment=photo.vk_attachment,
        sort_order=getattr(photo, 'sort_order', 0)
    ) for photo in photos]
    
    # Получаем информацию о группе, если товар в группе
    group_id = None
    group_name = None
    group_items = []
    is_group = False
    
    promo_badge_by_id: dict[int, Optional[str]] = {}
    counts_map: Dict[int, Tuple[int, int]] = {}
    if item.group_id:
        from api.products.models.item_group import ItemGroup
        group_result = await session.execute(
            select(ItemGroup).where(ItemGroup.id == item.group_id)
        )
        group = group_result.scalar_one_or_none()
        
        if group:
            group_id = group.id
            group_name = group.name
            is_group = True
            
            # Получаем ВСЕ товары в группе (включая текущий)
            group_items_result = await session.execute(
                select(Item).options(joinedload(Item.item_type_rel)).where(Item.group_id == item.group_id).order_by(Item.id)
            )
            all_group_items = group_items_result.unique().scalars().all()
            group_item_ids = [gi.id for gi in all_group_items]
            counts_map = await get_feed_like_dislike_counts_map(session, group_item_ids)
            promo_badge_by_id = await batch_system_photo_promo_badges(session, [item.id, *group_item_ids])
            group_has_stock_result = await session.execute(
                select(ItemStock.item_id).where(
                    and_(ItemStock.item_id.in_(group_item_ids), ItemStock.quantity > 0)
                ).distinct()
            )
            group_items_with_stock = {row[0] for row in group_has_stock_result.all()}
            
            # Формируем полные FeedItemResponse для всех товаров группы
            group_items = []
            for group_item in all_group_items:
                # Рассчитываем цену для каждого товара в группе
                item_price_rub = await calculate_item_price(group_item, ctx)
                
                # Получаем историю цен
                item_min_price, item_max_price = await get_price_history(group_item.id, session)
                if item_min_price is None or item_max_price is None:
                    item_min_price = item_price_rub
                    item_max_price = item_price_rub
                
                # Получаем фото товара
                item_photos_result = await session.execute(
                    select(ItemPhoto).where(ItemPhoto.item_id == group_item.id).order_by(ItemPhoto.id)
                )
                item_photos = item_photos_result.scalars().all()
                item_telegram_file_id = item_photos[0].telegram_file_id if item_photos else None
                item_vk_attachment = item_photos[0].vk_attachment if item_photos else None
                
                item_photos_list = [ItemPhotoResponse(
                    id=photo.id,
                    file_path=photo.file_path,
                    telegram_file_id=photo.telegram_file_id,
                    vk_attachment=photo.vk_attachment
                ) for photo in item_photos]
                
                # Преобразуем список размеров в строку через запятую
                size_str = None
                if group_item.size:
                    if isinstance(group_item.size, list):
                        size_str = ", ".join(str(s) for s in group_item.size)
                    else:
                        size_str = str(group_item.size)
                
                g_fixed = getattr(group_item, "fixed_price", None) if group_item.id in group_items_with_stock else None
                glc, gdc = like_dislike_for(counts_map, group_item.id)
                group_items.append(FeedItemResponse(
                    id=group_item.id,
                    name=group_item.name,
                    description=group_item.description,
                    price_rub=item_price_rub,
                    size=size_str,
                    min_price_week=item_min_price,
                    max_price_week=item_max_price,
                    telegram_file_id=item_telegram_file_id,
                    vk_attachment=item_vk_attachment,
                    photos=item_photos_list,
                    group_id=group_id,
                    group_name=group_name,
                    group_items=[],  # Не вкладываем рекурсивно
                    is_group=False,  # Это отдельный товар в группе
                    is_legit=group_item.is_legit,
                    fixed_price_rub=g_fixed,
                    photo_promo_badge=promo_badge_by_id.get(group_item.id),
                    feed_like_count=glc,
                    feed_dislike_count=gdc,
                ))
    
    # Преобразуем список размеров в строку через запятую
    size_str = None
    if item.size:
        if isinstance(item.size, list):
            size_str = ", ".join(str(s) for s in item.size)
        else:
            size_str = str(item.size)

    # Определяем, лайкнул ли пользователь этот товар
    liked_flag: Optional[bool] = None
    if user_id is not None:
        from api.products.models.like import Like

        like_result = await session.execute(
            select(Like).where(
                and_(
                    Like.user_id == user_id,
                    Like.item_id == item.id,
                    Like.action == "like",
                )
            )
        )
        liked_like = like_result.scalar_one_or_none()
        liked_flag = liked_like is not None
    
    # Позиции этого товара в корзине (при авторизованном запросе)
    in_cart_list: Optional[list] = None
    if user_id is not None:
        cart_result = await session.execute(
            select(Cart).where(
                and_(Cart.user_id == user_id, Cart.item_id == item.id)
            )
        )
        cart_rows = cart_result.scalars().all()
        in_cart_list = [
            InCartEntry(
                size=row.size,
                quantity=row.quantity,
                stock_type=row.stock_type,
                cart_item_id=row.id,
            )
            for row in cart_rows
        ]
    
    fixed_price_rub = getattr(item, "fixed_price", None) if has_stock else None
    size_chart_resp = None
    if item.size_chart:
        size_chart_resp = SizeChartResponse(id=item.size_chart.id, name=item.size_chart.name, grid=item.size_chart.grid)
    if not promo_badge_by_id:
        promo_badge_by_id = await batch_system_photo_promo_badges(session, [item.id])
    if not counts_map:
        counts_map = await get_feed_like_dislike_counts_map(session, [item.id])
    mlc, mdc = like_dislike_for(counts_map, item.id)
    return FeedItemResponse(
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
        group_id=group_id,
        group_name=group_name,
        group_items=group_items,
        is_group=is_group,
        is_legit=item.is_legit,
        price_history=price_history,
        liked=liked_flag,
        fixed_price_rub=fixed_price_rub,
        in_cart=in_cart_list,
        size_chart=size_chart_resp,
        photo_promo_badge=promo_badge_by_id.get(item.id),
        feed_like_count=mlc,
        feed_dislike_count=mdc,
    )


BUYOUT_QUEUE_HOLD_DAYS = 7
BUYOUT_LONG_POLL_MAX_SEC = 28.0
BUYOUT_LONG_POLL_SLEEP_SEC = 1.5


class ItemBuyoutQueueResponse(BaseModel):
    """Предзаказные «Выкуп»: по товару и общая волна (таймер по всей партии)."""

    count: int = Field(..., description="Число заказов «Выкуп» (предзаказ), в составе которых есть этот item_id")
    first_buyout_at: Optional[str] = Field(
        None,
        description="ISO 8601: самый ранний «Выкуп» именно с этим товаром (если count > 0)",
    )
    application_deadline_at: Optional[str] = Field(
        None,
        description="ISO 8601: дедлайн окна холда — первый предзаказный «Выкуп» по **всем** товарам + 7 суток",
    )
    global_buyout_count: int = Field(
        ...,
        description="Число всех предзаказных заказов «Выкуп» (любой состав)",
    )
    wave_first_buyout_at: Optional[str] = Field(
        None,
        description="ISO 8601: created_at самого раннего предзаказного «Выкуп» (основа для application_deadline_at)",
    )
    revision: str = Field(
        ...,
        description="Версия состояния для long poll (передавать в query revision)",
    )


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _first_and_deadline_iso(first_at: Optional[datetime]) -> Tuple[Optional[str], Optional[str]]:
    if first_at is None:
        return None, None
    ts = _normalize_utc(first_at)
    assert ts is not None
    first_iso = ts.isoformat()
    deadline_iso = (ts + timedelta(days=BUYOUT_QUEUE_HOLD_DAYS)).isoformat()
    return first_iso, deadline_iso


def _buyout_queue_revision(
    item_count: int,
    item_first: Optional[datetime],
    global_count: int,
    wave_first: Optional[datetime],
) -> str:
    def part(c: int, ft: Optional[datetime]) -> str:
        if ft is None:
            return f"{c}|"
        ts = _normalize_utc(ft)
        assert ts is not None
        return f"{c}|{ts.isoformat()}"

    return f"i{part(item_count, item_first)}g{part(global_count, wave_first)}"


async def _read_buyout_queue_state(session: AsyncSession, item_id: int) -> dict:
    """По товару + глобально по всем предзаказным «Выкуп» (общий дедлайн для таймера)."""
    match_sql = text(
        "EXISTS (SELECT 1 FROM jsonb_array_elements("
        "COALESCE((orders.order_data::jsonb)->'items', '[]'::jsonb)"
        ") AS elem "
        "WHERE (elem->>'item_id') IS NOT NULL AND (elem->>'item_id')::int = :iid)"
    ).bindparams(iid=item_id)
    result = await session.execute(
        select(func.count(Order.id), func.min(Order.created_at)).where(
            Order.status == "Выкуп",
            Order.is_from_stock.is_(False),
            match_sql,
        )
    )
    row = result.one()
    cnt = int(row[0] or 0)
    item_first: Optional[datetime] = row[1]

    result_g = await session.execute(
        select(func.count(Order.id), func.min(Order.created_at)).where(
            Order.status == "Выкуп",
            Order.is_from_stock.is_(False),
        )
    )
    row_g = result_g.one()
    g_cnt = int(row_g[0] or 0)
    wave_first: Optional[datetime] = row_g[1]

    item_first_iso, _ = _first_and_deadline_iso(item_first if cnt > 0 else None)
    wave_first_iso, wave_deadline_iso = _first_and_deadline_iso(wave_first if g_cnt > 0 else None)

    revision = _buyout_queue_revision(cnt, item_first, g_cnt, wave_first)

    return {
        "count": cnt,
        "first_buyout_at": item_first_iso,
        "application_deadline_at": wave_deadline_iso,
        "global_buyout_count": g_cnt,
        "wave_first_buyout_at": wave_first_iso,
        "revision": revision,
    }


@router.get("/items/{item_id}/buyout-queue", response_model=ItemBuyoutQueueResponse)
async def get_item_buyout_queue(
    item_id: int,
    wait: bool = Query(
        False,
        description="Long poll: ждать, пока revision изменится, или до таймаута (~28 с)",
    ),
    revision: Optional[str] = Query(
        None,
        description="Значение revision с прошлого ответа (обязательно при wait=true после снимка)",
    ),
    session: AsyncSession = Depends(get_session),
):
    """
    Публично: выкупы с этим товаром (count), все предзаказные выкупы (global_buyout_count),
    дедлайн окна холда по **самому раннему выкупу в целом** (application_deadline_at).
    При wait=true — удерживать соединение до смены данных или таймаута (клиент переподключается).
    """
    exists_row = await session.execute(select(Item.id).where(Item.id == item_id).limit(1))
    if exists_row.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Item not found")

    if not wait:
        data = await _read_buyout_queue_state(session, item_id)
        return ItemBuyoutQueueResponse(**data)

    if revision is None or revision == "":
        raise HTTPException(
            status_code=400,
            detail="При wait=true укажите query revision из ответа GET без wait",
        )

    loop = asyncio.get_running_loop()
    deadline = loop.time() + BUYOUT_LONG_POLL_MAX_SEC
    client_rev = revision

    while True:
        data = await _read_buyout_queue_state(session, item_id)
        if data["revision"] != client_rev:
            return ItemBuyoutQueueResponse(**data)
        if loop.time() >= deadline:
            return ItemBuyoutQueueResponse(**data)
        await asyncio.sleep(BUYOUT_LONG_POLL_SLEEP_SEC)


# --- Внутренние эндпоинты для скрипта ИИ-описаний (поле description) ---

class ItemForAiDescription(BaseModel):
    id: int
    name: str
    first_photo_path: str


class ForAiDescriptionList(BaseModel):
    items: List[ItemForAiDescription]
    total: int
    limit: int
    offset: int


class ItemInternalPhotosResponse(BaseModel):
    item_id: int
    photo_paths: List[str]
    item_type_name: Optional[str] = None


class InternalItemsByIdsRequest(BaseModel):
    item_ids: List[int] = Field(default_factory=list, max_length=500)


class InternalItemTitleRow(BaseModel):
    id: int
    name: str


class InternalItemsByIdsResponse(BaseModel):
    items: List[InternalItemTitleRow]


@router.post("/internal/items/by-ids", response_model=InternalItemsByIdsResponse)
async def internal_items_by_ids(
    body: InternalItemsByIdsRequest,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session),
):
    """Пакетно вернуть id и отображаемое имя товара (межсервисно, один запрос вместо N GET)."""
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Invalid internal token")
    raw: List[int] = []
    for x in body.item_ids:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if i > 0:
            raw.append(i)
    ids = list(dict.fromkeys(raw))[:500]
    if not ids:
        return InternalItemsByIdsResponse(items=[])
    result = await session.execute(select(Item.id, Item.name).where(Item.id.in_(ids)))
    rows = result.all()
    id_wanted = set(ids)
    items = [
        InternalItemTitleRow(id=int(r.id), name=str(r.name or ""))
        for r in rows
        if r.id is not None and int(r.id) in id_wanted
    ]
    return InternalItemsByIdsResponse(items=items)


@router.get("/internal/items/for-ai-description", response_model=ForAiDescriptionList)
async def list_items_for_ai_description(
    limit: int = 20,
    offset: int = 0,
    min_id: Optional[int] = Query(
        None,
        ge=1,
        description="Если задано — только товары с id >= min_id (продолжить скрипт с нужного id).",
    ),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session),
):
    """Список товаров с путём к первому фото для батчевой генерации ИИ-описаний (внутренний)."""
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Invalid internal token")
    first_photo_subq = (
        select(ItemPhoto.file_path)
        .where(ItemPhoto.item_id == Item.id)
        .order_by(ItemPhoto.sort_order, ItemPhoto.id)
        .limit(1)
        .scalar_subquery()
    )
    has_photo = exists(select(1).select_from(ItemPhoto).where(ItemPhoto.item_id == Item.id))
    count_where = has_photo if min_id is None else and_(has_photo, Item.id >= min_id)
    total_result = await session.execute(select(func.count(Item.id)).where(count_where))
    total = total_result.scalar() or 0
    list_where = has_photo if min_id is None else and_(has_photo, Item.id >= min_id)
    stmt = (
        select(Item.id, Item.name, first_photo_subq.label("first_photo_path"))
        .where(list_where)
        .order_by(Item.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        ItemForAiDescription(id=r.id, name=r.name, first_photo_path=r.first_photo_path or "")
        for r in rows
        if getattr(r, "first_photo_path", None)
    ]
    return ForAiDescriptionList(items=items, total=total, limit=limit, offset=offset)


@router.get("/internal/items/{item_id}/photos", response_model=ItemInternalPhotosResponse)
async def get_item_photos_internal(
    item_id: int,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session),
):
    """Внутренний endpoint: вернуть все file_path фото товара по id."""
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Invalid internal token")

    result = await session.execute(
        select(Item)
        .options(joinedload(Item.item_type_rel))
        .where(Item.id == item_id)
    )
    item = result.unique().scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    photos_result = await session.execute(
        select(ItemPhoto.file_path)
        .where(ItemPhoto.item_id == item_id)
        .order_by(
            func.coalesce(ItemPhoto.sort_order, 999999).asc(),
            ItemPhoto.id.asc(),
        )
    )
    photo_paths = [str(r[0]) for r in photos_result.all() if r and r[0]]
    item_type_name = item.item_type_rel.name if getattr(item, "item_type_rel", None) else None
    return ItemInternalPhotosResponse(
        item_id=item_id,
        photo_paths=photo_paths,
        item_type_name=item_type_name,
    )


class UpdateDescriptionBody(BaseModel):
    description: str


@router.patch("/internal/items/{item_id}/description")
async def update_item_description_internal(
    item_id: int,
    body: UpdateDescriptionBody,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session),
):
    """Обновить поле description товара (ИИ-описание). Внутренний эндпоинт."""
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Invalid internal token")
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.description = body.description
    await session.commit()
    return {"id": item_id, "description": body.description}
