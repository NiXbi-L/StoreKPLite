"""
Роутер для действий с товарами (лайк, дизлайк, сохранение, просмотр)
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from os import getenv
from typing import Optional, List

from api.products.database.database import get_session
from api.products.models.item import Item
from api.products.models.like import Like
from api.products.models.item_stock import ItemStock
from api.products.models.item_reservation import ItemReservation
from api.products.utils.likes_cache import bump_likes_revisions
from api.shared.auth import get_user_id_for_request
from sqlalchemy import and_

router = APIRouter()

REDIS_URL = getenv("REDIS_URL", "redis://products-redis:6379/0")


async def mark_item_as_viewed(user_id: int, item_id: int, platform: str = "tg"):
    """Пометить товар как показанный (24 часа для повторного показа)"""
    try:
        import redis.asyncio as redis
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
        key = f"feed_history:{platform}:{user_id}:{item_id}"
        await redis_client.setex(key, 86400, "1")  # 24 часа
        await redis_client.close()
    except Exception:
        pass


class ItemActionRequest(BaseModel):
    action: str  # "like", "dislike", "save", "view"


@router.post("/items/{item_id}/action")
async def perform_item_action(
    item_id: int,
    request: ItemActionRequest,
    user_id: int = Depends(get_user_id_for_request),
    platform: Optional[str] = Header(None, alias="X-Platform"),
    session: AsyncSession = Depends(get_session)
):
    """
    Выполнить действие с товаром (лайк, дизлайк, сохранение, просмотр)
    """
    if request.action not in ["like", "dislike", "save", "view"]:
        raise HTTPException(status_code=400, detail="Неподдерживаемое действие")
    
    # Проверяем, существует ли товар
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    # Для действия "view" помечаем в Redis для повторного показа через время
    if request.action == "view":
        platform_for_redis = platform or "tg"
        await mark_item_as_viewed(user_id, item_id, platform_for_redis)
        return {"success": True, "action": "view"}
    
    # Для лайков/дизлайков/сохранений сохраняем в БД только для конкретного товара
    existing_result = await session.execute(
        select(Like).where(
            and_(
                Like.user_id == user_id,
                Like.item_id == item_id
            )
        )
    )
    existing_like = existing_result.scalar_one_or_none()

    old_action = str(existing_like.action) if existing_like else None
    if existing_like:
        existing_like.action = request.action
    else:
        session.add(
            Like(
                user_id=user_id,
                item_id=item_id,
                action=request.action,
            )
        )

    await session.commit()

    plat = platform or "tg"
    bump_targets = {a for a in (old_action, request.action) if a and a in ("like", "dislike", "save")}
    if bump_targets:
        await bump_likes_revisions(plat, user_id, bump_targets)

    return {
        "success": True,
        "action": request.action,
        "items_affected": 1
    }


class ReserveItemRequest(BaseModel):
    size: str
    quantity: int


@router.post("/items/{item_id}/reserve")
async def reserve_item(
    item_id: int,
    body: ReserveItemRequest,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """Зарезервировать товар (размер, количество). Проверяется наличие на складе."""
    if body.quantity < 1:
        raise HTTPException(status_code=400, detail="Количество должно быть больше 0")
    item_result = await session.execute(select(Item).where(Item.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")
    stock_result = await session.execute(
        select(ItemStock).where(
            and_(
                ItemStock.item_id == item_id,
                ItemStock.size == body.size,
                ItemStock.quantity >= body.quantity,
            )
        )
    )
    stock = stock_result.scalar_one_or_none()
    if not stock:
        raise HTTPException(
            status_code=400,
            detail="Недостаточно на складе или нет такого размера",
        )
    reservation = ItemReservation(
        item_id=item_id,
        size=body.size,
        quantity=body.quantity,
        user_id=user_id,
        status="active",
    )
    session.add(reservation)
    await session.commit()
    await session.refresh(reservation)
    return {"success": True, "reservation_id": reservation.id}


@router.delete("/items/{item_id}/action")
async def remove_item_action(
    item_id: int,
    user_id: int = Depends(get_user_id_for_request),
    platform: Optional[str] = Header(None, alias="X-Platform"),
    session: AsyncSession = Depends(get_session),
):
    """
    Удалить действие с товаром (убрать из лайков/дизлайков/сохраненных)
    Если товар в группе, удаляет действие со всех товаров группы
    """
    # Проверяем, существует ли товар
    item_result = await session.execute(select(Item).where(Item.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    # Удаляем действие только для конкретного товара
    like_result = await session.execute(
        select(Like).where(
            and_(
                Like.user_id == user_id,
                Like.item_id == item_id
            )
        )
    )
    like = like_result.scalar_one_or_none()
    
    action_for_bump = None
    if like:
        action_for_bump = str(like.action)
        await session.delete(like)

    await session.commit()

    if action_for_bump in ("like", "dislike", "save"):
        plat = platform or "tg"
        await bump_likes_revisions(plat, user_id, {action_for_bump})

    return {
        "success": True,
        "items_affected": 1
    }

