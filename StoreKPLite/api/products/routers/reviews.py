"""
Роутер отзывов о товарах: summary и список с фильтрами по дате и звёздам.
"""
import logging
from os import getenv
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.products.database.database import get_session
from api.products.models.item_review import ItemReview, ItemReviewPhoto

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["reviews"])

USERS_SERVICE_URL = getenv("USERS_SERVICE_URL", "http://users-service:8001")


async def _user_display(user_id: int) -> dict:
    """Получить avatar_url и имя пользователя из users service. Приоритет: firstname, иначе маска по phone."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{USERS_SERVICE_URL}/users/{user_id}", timeout=3.0)
            if r.status_code != 200:
                return {"user_name": "Пользователь", "user_avatar_url": None}
            data = r.json()
            name = "Пользователь"
            firstname = (data.get("firstname") or "").strip()
            if firstname:
                name = firstname
            elif data.get("phone_local"):
                pl = str(data["phone_local"])
                name = f"Пользователь ***{pl[-4:]}" if len(pl) >= 4 else "Пользователь"
            return {"user_name": name, "user_avatar_url": data.get("avatar_url")}
    except Exception as e:
        logger.debug("users service for review author: %s", e)
        return {"user_name": "Пользователь", "user_avatar_url": None}


@router.get("/{item_id}/reviews/summary")
async def get_item_reviews_summary(
    item_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Средняя оценка и общее количество отзывов по товару (для кнопки «Отзывы N»)."""
    st_count = select(func.count(ItemReview.id)).where(ItemReview.item_id == item_id)
    st_avg = select(func.coalesce(func.avg(ItemReview.rating), 0)).where(ItemReview.item_id == item_id)
    count_result = await session.execute(st_count)
    avg_result = await session.execute(st_avg)
    total_count = count_result.scalar() or 0
    average_rating = float(avg_result.scalar() or 0)
    return {"average_rating": round(average_rating, 2), "total_count": total_count}


@router.get("/{item_id}/reviews")
async def get_item_reviews(
    item_id: int,
    sort: Optional[str] = Query("date_desc", description="date_asc | date_desc"),
    stars: Optional[int] = Query(None, ge=1, le=5, description="Фильтр по оценке 1-5"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Список отзывов с фильтрами по дате и звёздам."""
    base = select(ItemReview).where(ItemReview.item_id == item_id)
    if stars is not None:
        base = base.where(ItemReview.rating == stars)
    base = base.options(selectinload(ItemReview.photos))
    if sort == "date_asc":
        base = base.order_by(ItemReview.created_at.asc())
    else:
        base = base.order_by(ItemReview.created_at.desc())
    base = base.offset(offset).limit(limit)
    result = await session.execute(base)
    reviews = result.scalars().unique().all()

    # Общая сводка по товару (без фильтра по звёздам)
    st_count = select(func.count(ItemReview.id)).where(ItemReview.item_id == item_id)
    st_avg = select(func.coalesce(func.avg(ItemReview.rating), 0)).where(ItemReview.item_id == item_id)
    count_result = await session.execute(st_count)
    avg_result = await session.execute(st_avg)
    total_count = count_result.scalar() or 0
    average_rating = round(float(avg_result.scalar() or 0), 2)

    # Имена и аватарки из users
    user_ids = list({r.user_id for r in reviews})
    users_info = {}
    for uid in user_ids:
        users_info[uid] = await _user_display(uid)

    out = []
    for r in reviews:
        photos = [p.file_path for p in (r.photos or [])]
        info = users_info.get(r.user_id, {"user_name": "Пользователь", "user_avatar_url": None})
        out.append({
            "id": r.id,
            "item_id": r.item_id,
            "user_id": r.user_id,
            "user_name": info["user_name"],
            "user_avatar_url": info["user_avatar_url"],
            "rating": r.rating,
            "comment": r.comment or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "photos": photos,
        })
    return {
        "average_rating": average_rating,
        "total_count": total_count,
        "reviews": out,
    }
