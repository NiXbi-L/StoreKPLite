"""
Эндпоинты для пресетов доставки пользователя в Delivery‑сервисе.

Используют отдельную БД delivery-service и JWT миниаппы (users-service).
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from api.delivery.database.database import get_session
from api.delivery.models.user_delivery_data import UserDeliveryData
from api.delivery.schemas.user_delivery_data import (
    UserDeliveryDataResponse,
    UserDeliveryDataCreate,
    UserDeliveryDataUpdate,
)
from api.shared.auth import get_user_id_for_request, get_user_id_and_profile_phone

router = APIRouter()

_PROFILE_PHONE_REQUIRED_MESSAGE = (
    "Добавьте номер телефона в профиль, чтобы мы могли с вами связаться. "
    "Укажите номер в разделе «Профиль» в приложении."
)


@router.get("/user-delivery-data/list", response_model=List[UserDeliveryDataResponse])
async def get_user_delivery_data_list(
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """
    Получить все пресеты доставки текущего пользователя.
    """
    result = await session.execute(
        select(UserDeliveryData)
        .where(UserDeliveryData.user_id == user_id)
        .order_by(UserDeliveryData.is_default.desc(), UserDeliveryData.created_at.desc())
    )
    data_list = result.scalars().all()
    return data_list


def _norm(s: Optional[str]) -> Optional[str]:
    """Нормализация для сравнения: пустая строка как None."""
    if s is None:
        return None
    t = (s or "").strip()
    return t if t else None


def _preset_equals(a: UserDeliveryData, request: UserDeliveryDataCreate) -> bool:
    """Пресет совпадает с запросом по всем полям (сравниваем нормализованные значения)."""
    return (
        (a.delivery_method_id == request.delivery_method_id)
        and (_norm(a.phone_number) == _norm(request.phone_number))
        and (_norm(a.address) == _norm(request.address))
        and (_norm(a.recipient_name) == _norm(request.recipient_name))
        and (_norm(a.postal_code) == _norm(request.postal_code))
        and (a.city_code == request.city_code)
        and (_norm(a.cdek_delivery_point_code) == _norm(request.cdek_delivery_point_code))
    )


@router.post("/user-delivery-data", response_model=UserDeliveryDataResponse)
async def create_or_update_user_delivery_data(
    request: UserDeliveryDataCreate,
    user_id_and_phone: tuple[int, Optional[str]] = Depends(get_user_id_and_profile_phone),
    session: AsyncSession = Depends(get_session),
):
    """
    Создать пресет доставки или вернуть существующий без изменений.
    Требуется номер телефона в профиле пользователя (для связи с владельцем аккаунта).
    """
    user_id, profile_phone = user_id_and_phone
    if not (profile_phone and profile_phone.strip()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_PROFILE_PHONE_REQUIRED_MESSAGE,
        )
    result = await session.execute(
        select(UserDeliveryData)
        .where(UserDeliveryData.user_id == user_id)
        .order_by(UserDeliveryData.created_at.desc())
    )
    all_presets = list(result.scalars().all())

    for existing in all_presets:
        if _preset_equals(existing, request):
            return existing

    is_first = len(all_presets) == 0
    new_data = UserDeliveryData(
        user_id=user_id,
        phone_number=request.phone_number,
        delivery_method_id=request.delivery_method_id,
        address=request.address,
        recipient_name=request.recipient_name,
        postal_code=request.postal_code,
        city_code=request.city_code,
        cdek_delivery_point_code=request.cdek_delivery_point_code,
        is_default=is_first,
    )
    session.add(new_data)
    await session.commit()
    await session.refresh(new_data)
    return new_data


@router.put("/user-delivery-data/{preset_id}", response_model=UserDeliveryDataResponse)
async def update_user_delivery_data(
    preset_id: int,
    request: UserDeliveryDataUpdate,
    user_id_and_phone: tuple[int, Optional[str]] = Depends(get_user_id_and_profile_phone),
    session: AsyncSession = Depends(get_session),
):
    """
    Обновить пресет доставки по id (только свой пресет).
    Требуется номер телефона в профиле.
    """
    user_id, profile_phone = user_id_and_phone
    if not (profile_phone and profile_phone.strip()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_PROFILE_PHONE_REQUIRED_MESSAGE,
        )
    result = await session.execute(
        select(UserDeliveryData).where(
            UserDeliveryData.id == preset_id,
            UserDeliveryData.user_id == user_id,
        )
    )
    data = result.scalar_one_or_none()
    if not data:
        raise HTTPException(
            status_code=404,
            detail="Данные доставки не найдены. Используйте POST для создания нового.",
        )

    if request.phone_number is not None:
        data.phone_number = request.phone_number
    if request.delivery_method_id is not None:
        data.delivery_method_id = request.delivery_method_id
    if request.address is not None:
        data.address = request.address
    if request.recipient_name is not None:
        data.recipient_name = request.recipient_name
    if request.postal_code is not None:
        data.postal_code = request.postal_code
    if request.city_code is not None:
        data.city_code = request.city_code
    if request.cdek_delivery_point_code is not None:
        data.cdek_delivery_point_code = request.cdek_delivery_point_code

    await session.commit()
    await session.refresh(data)
    return data


@router.put("/user-delivery-data/{preset_id}/set-default", response_model=UserDeliveryDataResponse)
async def set_default_user_delivery_data(
    preset_id: int,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """
    Сделать пресет основным способом доставки. У остальных пресетов пользователя is_default сбрасывается.
    """
    result = await session.execute(
        select(UserDeliveryData).where(
            UserDeliveryData.id == preset_id,
            UserDeliveryData.user_id == user_id,
        )
    )
    data = result.scalar_one_or_none()
    if not data:
        raise HTTPException(status_code=404, detail="Данные доставки не найдены")

    await session.execute(
        update(UserDeliveryData)
        .where(UserDeliveryData.user_id == user_id)
        .values(is_default=False)
    )
    data.is_default = True
    await session.commit()
    await session.refresh(data)
    return data


@router.delete("/user-delivery-data/{preset_id}")
async def delete_user_delivery_data(
    preset_id: int,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """
    Удалить пресет доставки по id (только свой пресет).
    """
    result = await session.execute(
        select(UserDeliveryData).where(
            UserDeliveryData.id == preset_id,
            UserDeliveryData.user_id == user_id,
        )
    )
    data = result.scalar_one_or_none()
    if not data:
        raise HTTPException(status_code=404, detail="Данные доставки не найдены")

    await session.delete(data)
    await session.commit()
    return {"message": "Данные доставки удалены"}

