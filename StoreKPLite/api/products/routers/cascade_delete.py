"""
Роутер для каскадного удаления и проверки связей
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any, Optional
from os import getenv

from api.products.database.database import get_session
from api.products.models.order import Order
from api.products.models.cart import Cart
from api.products.models.like import Like
from api.products.models.item_reservation import ItemReservation
from api.products.models.item_review import ItemReview

INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")

router = APIRouter()


def verify_internal_token(x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")):
    """Проверка внутреннего токена"""
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    return True


# Маппинг полей на модели
FIELD_TO_MODEL = {
    "user_id": {
        "Order": Order,
        "Cart": Cart,
        "Like": Like,
    }
}


@router.get("/internal/db/check-foreign-keys/{field_name}/{record_id}")
async def check_foreign_keys(
    field_name: str,
    record_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(verify_internal_token)
) -> Dict[str, Any]:
    """Проверить наличие связанных записей по foreign key"""
    
    if field_name not in FIELD_TO_MODEL:
        return {"has_relations": False, "relations": []}
    
    relations = []
    models = FIELD_TO_MODEL[field_name]
    
    for table_name, model_class in models.items():
        # Получаем количество связанных записей
        field = getattr(model_class, field_name)
        result = await session.execute(
            select(func.count(model_class.id)).where(field == record_id)
        )
        count = result.scalar() or 0
        
        if count > 0:
            relations.append({
                "service": "products",
                "table": table_name,
                "field": field_name,
                "count": count
            })
    
    return {
        "has_relations": len(relations) > 0,
        "relations": relations
    }


@router.delete("/internal/db/cascade-delete/{field_name}/{record_id}")
async def cascade_delete(
    field_name: str,
    record_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(verify_internal_token)
) -> Dict[str, Any]:
    """Каскадное удаление связанных записей"""
    
    if field_name not in FIELD_TO_MODEL:
        return {"deleted": 0, "tables": []}
    
    deleted_tables = []
    models = FIELD_TO_MODEL[field_name]
    
    for table_name, model_class in models.items():
        field = getattr(model_class, field_name)
        
        # Получаем записи для удаления
        result = await session.execute(
            select(model_class).where(field == record_id)
        )
        records = result.scalars().all()
        
        if records:
            count = len(records)
            for record in records:
                await session.delete(record)
            await session.commit()
            
            deleted_tables.append({
                "service": "products",
                "table": table_name,
                "deleted_count": count
            })
    
    return {
        "deleted": sum(t["deleted_count"] for t in deleted_tables),
        "tables": deleted_tables
    }


@router.delete("/internal/users/{user_id}/delete-all-data")
async def delete_all_user_data(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(verify_internal_token),
) -> Dict[str, Any]:
    """
    Удалить все данные пользователя в сервисе products:
    резервы, отзывы (и фото), корзина, лайки, заказы (доставка по каскаду).
    Вызывается из users-service при удалении пользователя.
    """
    deleted_tables = []
    # 1. Резервы (user_id)
    r = await session.execute(select(ItemReservation).where(ItemReservation.user_id == user_id))
    reservations = r.scalars().all()
    for rec in reservations:
        await session.delete(rec)
    if reservations:
        await session.commit()
        deleted_tables.append({"table": "item_reservations", "deleted_count": len(reservations)})
    # 2. Отзывы (user_id) — фото удалятся по cascade
    r = await session.execute(select(ItemReview).where(ItemReview.user_id == user_id))
    reviews = r.scalars().all()
    for rec in reviews:
        await session.delete(rec)
    if reviews:
        await session.commit()
        deleted_tables.append({"table": "item_reviews", "deleted_count": len(reviews)})
    # 3. Корзина
    r = await session.execute(select(Cart).where(Cart.user_id == user_id))
    carts = r.scalars().all()
    for rec in carts:
        await session.delete(rec)
    if carts:
        await session.commit()
        deleted_tables.append({"table": "cart", "deleted_count": len(carts)})
    # 4. Лайки
    r = await session.execute(select(Like).where(Like.user_id == user_id))
    likes = r.scalars().all()
    for rec in likes:
        await session.delete(rec)
    if likes:
        await session.commit()
        deleted_tables.append({"table": "likes", "deleted_count": len(likes)})
    # 5. Заказы (order_delivery удалится по CASCADE)
    r = await session.execute(select(Order).where(Order.user_id == user_id))
    orders = r.scalars().all()
    for rec in orders:
        await session.delete(rec)
    if orders:
        await session.commit()
        deleted_tables.append({"table": "orders", "deleted_count": len(orders)})
    return {
        "service": "products",
        "user_id": user_id,
        "deleted": sum(t["deleted_count"] for t in deleted_tables),
        "tables": deleted_tables,
    }

