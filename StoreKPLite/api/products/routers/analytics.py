"""
Роутер для аналитики (внутренние endpoints для users-service)
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct, desc, case
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, date
from os import getenv
import httpx
import logging

from api.products.database.database import get_session
from api.products.models.like import Like
from api.products.models.order import Order
from api.products.models.cart import Cart
from api.products.models.item import Item

logger = logging.getLogger(__name__)

router = APIRouter()

# Топ лайков в админ-аналитике: комбинация «объём» + «перевес».
# like_score = likes_weight×лайки + margin_weight×(лайки−дизлайки) — лайки тянут сильнее, чем один только перевес.
# Топ дизлайков сортируется по старому: сначала перевес (дизлайки−лайки), затем число дизлайков.
_ADMIN_FEED_TOP_LIKES_WEIGHT = 3
_ADMIN_FEED_TOP_LIKE_MARGIN_WEIGHT = 1

INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")
USERS_SERVICE_URL = getenv("USERS_SERVICE_URL", "http://users-service:8001")


def check_internal_token(token: Optional[str] = None) -> bool:
    """Проверка внутреннего токена для межсервисного взаимодействия"""
    if not token:
        return False
    clean_token = token.replace("Bearer ", "").strip() if token.startswith("Bearer") else token.strip()
    return clean_token == INTERNAL_TOKEN


@router.get("/internal/analytics/likes")
async def get_likes_analytics(
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")
):
    """Получить аналитические данные о лайках (внутренний endpoint)"""
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # Количество уникальных пользователей с лайками
    users_with_like_result = await session.execute(
        select(func.count(distinct(Like.user_id))).where(Like.action == "like")
    )
    users_with_like = users_with_like_result.scalar() or 0
    
    # Среднее время от регистрации до первого лайка
    # Получаем список user_id с датами первого лайка
    first_like_result = await session.execute(
        select(
            Like.user_id,
            func.min(Like.created_at).label("first_like_at"),
        )
        .where(Like.action == "like")
        .group_by(Like.user_id)
    )
    first_likes = first_like_result.all()
    
    avg_start_to_like_seconds = 0.0
    if first_likes:
        try:
            # Получаем даты регистрации пользователей из users-service
            user_ids = [row[0] for row in first_likes]
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{USERS_SERVICE_URL}/internal/analytics/calc-avg-time",
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    json={
                        "events": [
                            {"user_id": row[0], "event_at": row[1].isoformat() if isinstance(row[1], datetime) else str(row[1])}
                            for row in first_likes
                        ]
                    },
                    timeout=10.0
                )
                if response.status_code == 200:
                    avg_start_to_like_seconds = response.json().get("avg_seconds", 0.0)
        except Exception as e:
            logger.error(f"Ошибка при получении среднего времени до лайка: {e}", exc_info=True)
    
    # Динамика лайков по дням за последние 30 дней
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=29)
    
    # Только свайп «вправо» в ленте; dislike/save считаются в business-summary
    likes_by_day_result = await session.execute(
        select(
            func.date_trunc("day", Like.created_at).label("day"),
            func.count(Like.id),
        )
        .where(Like.created_at >= start_date, Like.action == "like")
        .group_by("day")
        .order_by("day")
    )
    likes_by_day_raw = likes_by_day_result.all()
    
    likes_by_day_labels = []
    likes_by_day_values = []
    for day_value, count_value in likes_by_day_raw:
        if isinstance(day_value, datetime):
            label = day_value.date().isoformat()
        else:
            label = str(day_value)
        likes_by_day_labels.append(label)
        likes_by_day_values.append(int(count_value or 0))
    
    return {
        "users_with_like": users_with_like,
        "avg_start_to_like_seconds": avg_start_to_like_seconds,
        "likes_by_day_labels": likes_by_day_labels,
        "likes_by_day_values": likes_by_day_values
    }


@router.get("/internal/analytics/orders")
async def get_orders_analytics(
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")
):
    """Получить аналитические данные о заказах (внутренний endpoint)"""
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # Количество уникальных пользователей с заказами
    users_with_order_result = await session.execute(
        select(func.count(distinct(Order.user_id))).where(Order.user_id.is_not(None))
    )
    users_with_order = users_with_order_result.scalar() or 0
    
    # Среднее время от регистрации до первого заказа и от первого лайка до первого заказа
    first_order_result = await session.execute(
        select(
            Order.user_id,
            func.min(Order.created_at).label("first_order_at"),
        )
        .where(Order.user_id.is_not(None))
        .group_by(Order.user_id)
    )
    first_orders = first_order_result.all()
    
    # Получаем данные о первых лайках
    first_like_result = await session.execute(
        select(
            Like.user_id,
            func.min(Like.created_at).label("first_like_at"),
        )
        .where(Like.action == "like")
        .group_by(Like.user_id)
    )
    first_likes = first_like_result.all()
    
    avg_start_to_order_seconds = 0.0
    avg_like_to_order_seconds = 0.0
    if first_orders:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{USERS_SERVICE_URL}/internal/analytics/calc-avg-time-to-order",
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    json={
                        "first_orders": [
                            {"user_id": row[0], "event_at": row[1].isoformat() if isinstance(row[1], datetime) else str(row[1])}
                            for row in first_orders
                        ],
                        "first_likes": [
                            {"user_id": row[0], "event_at": row[1].isoformat() if isinstance(row[1], datetime) else str(row[1])}
                            for row in first_likes
                        ]
                    },
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    avg_start_to_order_seconds = data.get("avg_start_to_order_seconds", 0.0)
                    avg_like_to_order_seconds = data.get("avg_like_to_order_seconds", 0.0)
        except Exception as e:
            logger.error(f"Ошибка при получении среднего времени до заказа: {e}", exc_info=True)
    
    # Динамика заказов по дням за последние 30 дней
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=29)
    
    orders_by_day_result = await session.execute(
        select(
            func.date_trunc("day", Order.created_at).label("day"),
            func.count(Order.id),
        )
        .where(Order.created_at >= start_date)
        .group_by("day")
        .order_by("day")
    )
    orders_by_day_raw = orders_by_day_result.all()
    
    orders_by_day_labels = []
    orders_by_day_values = []
    for day_value, count_value in orders_by_day_raw:
        if isinstance(day_value, datetime):
            label = day_value.date().isoformat()
        else:
            label = str(day_value)
        orders_by_day_labels.append(label)
        orders_by_day_values.append(int(count_value or 0))
    
    return {
        "users_with_order": users_with_order,
        "avg_start_to_order_seconds": avg_start_to_order_seconds,
        "avg_like_to_order_seconds": avg_like_to_order_seconds,
        "orders_by_day_labels": orders_by_day_labels,
        "orders_by_day_values": orders_by_day_values
    }


@router.get("/internal/analytics/business-summary")
async def get_business_summary(
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    """Сводка по каталогу, корзине, заказам и лайкам (внутренний endpoint)."""
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    items_count = int(
        (await session.execute(select(func.count()).select_from(Item))).scalar() or 0
    )
    orders_count = int(
        (await session.execute(select(func.count()).select_from(Order))).scalar() or 0
    )

    status_rows = await session.execute(select(Order.status, func.count(Order.id)).group_by(Order.status))
    orders_by_status: Dict[str, int] = {}
    for st, cnt in status_rows.all():
        key = (st or "").strip() or "—"
        orders_by_status[key] = int(cnt or 0)

    cart_users = int(
        (await session.execute(select(func.count(distinct(Cart.user_id))))).scalar() or 0
    )
    cart_lines = int(
        (await session.execute(select(func.count()).select_from(Cart))).scalar() or 0
    )

    orders_with_user = int(
        (
            await session.execute(
                select(func.count(distinct(Order.user_id))).where(Order.user_id.is_not(None))
            )
        ).scalar()
        or 0
    )

    paid_pos = await session.execute(
        select(func.count(distinct(Order.user_id))).where(
            Order.user_id.is_not(None),
            Order.paid_amount.is_not(None),
            Order.paid_amount > 0,
        )
    )
    users_with_order_paid_positive = int(paid_pos.scalar() or 0)

    today = datetime.utcnow().date()
    start_date = today - timedelta(days=29)

    likes_action_result = await session.execute(
        select(Like.action, func.count(Like.id))
        .where(Like.created_at >= start_date)
        .group_by(Like.action)
    )
    likes_by_action_30d: Dict[str, int] = {}
    for action, cnt in likes_action_result.all():
        likes_by_action_30d[action or "—"] = int(cnt or 0)

    cart_by_day_result = await session.execute(
        select(
            func.date_trunc("day", Cart.created_at).label("day"),
            func.count(Cart.id),
        )
        .where(Cart.created_at >= start_date)
        .group_by("day")
        .order_by("day")
    )
    cart_by_day_raw = cart_by_day_result.all()
    cart_adds_by_day_labels: List[str] = []
    cart_adds_by_day_values: List[int] = []
    for day_value, count_value in cart_by_day_raw:
        if isinstance(day_value, datetime):
            label = day_value.date().isoformat()
        else:
            label = str(day_value)
        cart_adds_by_day_labels.append(label)
        cart_adds_by_day_values.append(int(count_value or 0))

    return {
        "items_count": items_count,
        "orders_count": orders_count,
        "orders_by_status": orders_by_status,
        "distinct_users_with_cart": cart_users,
        "cart_line_items": cart_lines,
        "distinct_users_with_order": orders_with_user,
        "distinct_users_with_order_paid_positive": users_with_order_paid_positive,
        "likes_by_action_30d": likes_by_action_30d,
        "cart_adds_by_day_labels": cart_adds_by_day_labels,
        "cart_adds_by_day_values": cart_adds_by_day_values,
    }


@router.get("/internal/analytics/feed-item-leaderboards")
async def feed_item_leaderboards(
    limit: int = 30,
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    """
    Топ товаров по ленте: лайки — комбинированный рейтинг (вес у числа лайков выше, чем у перевеса);
    дизлайки — по перевесу (дизлайки − лайки), затем по числу дизлайков (только где dislikes > likes).
    """
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    lim = min(max(int(limit or 30), 1), 100)

    likes_col = func.coalesce(func.sum(case((Like.action == "like", 1), else_=0)), 0).label("likes")
    dislikes_col = func.coalesce(func.sum(case((Like.action == "dislike", 1), else_=0)), 0).label("dislikes")
    agg = (
        select(Like.item_id.label("iid"), likes_col, dislikes_col).group_by(Like.item_id).subquery()
    )
    like_skew = (agg.c.likes - agg.c.dislikes).label("like_skew")
    dislike_skew = (agg.c.dislikes - agg.c.likes).label("dislike_skew")
    like_rank_score = (
        _ADMIN_FEED_TOP_LIKES_WEIGHT * agg.c.likes
        + _ADMIN_FEED_TOP_LIKE_MARGIN_WEIGHT * (agg.c.likes - agg.c.dislikes)
    ).label("like_rank_score")

    top_liked = await session.execute(
        select(Item.id, Item.name, agg.c.likes, agg.c.dislikes, like_skew, like_rank_score)
        .join(agg, Item.id == agg.c.iid)
        .order_by(
            desc(like_rank_score),
            desc(agg.c.likes),
            desc(like_skew),
        )
        .limit(lim)
    )
    top_disliked = await session.execute(
        select(Item.id, Item.name, agg.c.likes, agg.c.dislikes, dislike_skew)
        .join(agg, Item.id == agg.c.iid)
        .where(agg.c.dislikes > agg.c.likes)
        .order_by(desc(dislike_skew), desc(agg.c.dislikes))
        .limit(lim)
    )

    def _rows_like(rows):
        return [
            {
                "item_id": int(r[0]),
                "name": r[1] or "",
                "likes": int(r[2] or 0),
                "dislikes": int(r[3] or 0),
                "skew": int(r[4] or 0),
                "rank_score": int(r[5] or 0),
            }
            for r in rows.all()
        ]

    def _rows_dislike(rows):
        return [
            {
                "item_id": int(r[0]),
                "name": r[1] or "",
                "likes": int(r[2] or 0),
                "dislikes": int(r[3] or 0),
                "skew": int(r[4] or 0),
            }
            for r in rows.all()
        ]

    return {
        "limit": lim,
        "top_like_skew": _rows_like(top_liked),
        "top_dislike_skew": _rows_dislike(top_disliked),
        "top_like_rank_weights": {
            "likes": _ADMIN_FEED_TOP_LIKES_WEIGHT,
            "margin": _ADMIN_FEED_TOP_LIKE_MARGIN_WEIGHT,
        },
    }

