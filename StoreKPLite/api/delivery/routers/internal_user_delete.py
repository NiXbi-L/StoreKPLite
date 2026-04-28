"""
Внутренний эндпоинт для удаления всех данных пользователя (вызов из users-service).
"""
from typing import Optional, Dict, Any
from os import getenv

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.delivery.database.database import get_session
from api.delivery.models.user_delivery_data import UserDeliveryData

INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")
router = APIRouter()


def verify_internal_token(x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")):
    if not x_internal_token or x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    return True


@router.delete("/internal/users/{user_id}/delete-all-data")
async def delete_all_user_data(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(verify_internal_token),
) -> Dict[str, Any]:
    """Удалить все пресеты доставки пользователя. Вызывается из users-service при удалении пользователя."""
    result = await session.execute(select(UserDeliveryData).where(UserDeliveryData.user_id == user_id))
    records = result.scalars().all()
    for rec in records:
        await session.delete(rec)
    if records:
        await session.commit()
    return {
        "service": "delivery",
        "user_id": user_id,
        "deleted": len(records),
        "tables": [{"table": "user_delivery_data", "deleted_count": len(records)}] if records else [],
    }
