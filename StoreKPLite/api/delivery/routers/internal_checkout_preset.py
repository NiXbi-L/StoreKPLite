"""
Внутренний снимок пресета доставки для чекаута (products-service).

Миниапп может передавать только delivery_preset_id; products подтягивает
адрес, индекс, код города/ПВЗ СДЭК и код способа доставки из БД delivery.
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.delivery.database.database import get_session
from api.delivery.models.user_delivery_data import UserDeliveryData
from api.delivery.routers.methods import _map_method_to_public

router = APIRouter()

INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")


async def _verify_internal_token(x_internal_token: Optional[str]) -> None:
    if not x_internal_token or x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")


class CheckoutPresetSnapshot(BaseModel):
    """Поля пресета, нужные products для delivery_snapshot и расчёта доставки."""

    preset_id: int
    user_id: int
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city_code: Optional[int] = None
    cdek_delivery_point_code: Optional[str] = None
    recipient_name: Optional[str] = None
    phone_number: Optional[str] = None
    delivery_method_code: Optional[str] = None


@router.get(
    "/internal/user-delivery-data/checkout-snapshot",
    response_model=CheckoutPresetSnapshot,
)
async def checkout_preset_snapshot(
    user_id: int = Query(..., ge=1, description="ID пользователя (users-service)"),
    preset_id: int = Query(..., ge=1, description="ID пресета user_delivery_data"),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session),
):
    """
    Снимок сохранённого адреса для чекаута. Только по internal token + проверка user_id.
    """
    await _verify_internal_token(x_internal_token)
    result = await session.execute(
        select(UserDeliveryData)
        .options(selectinload(UserDeliveryData.delivery_method))
        .where(
            UserDeliveryData.id == preset_id,
            UserDeliveryData.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Пресет доставки не найден")

    method_code: Optional[str] = None
    if row.delivery_method is not None:
        method_code = _map_method_to_public(row.delivery_method).code

    return CheckoutPresetSnapshot(
        preset_id=row.id,
        user_id=row.user_id,
        address=row.address,
        postal_code=row.postal_code,
        city_code=row.city_code,
        cdek_delivery_point_code=row.cdek_delivery_point_code,
        recipient_name=row.recipient_name,
        phone_number=row.phone_number,
        delivery_method_code=method_code,
    )
