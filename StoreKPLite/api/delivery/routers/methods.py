"""
Публичные и внутренние эндпоинты для способов доставки.

Задача этого роутера — отдать фронту список способов доставки
с информацией о том, какие поля нужно собрать с пользователя
для каждого способа.
"""
import os
from typing import List, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.delivery.database.database import get_session
from api.delivery.models.delivery_method import DeliveryMethod


router = APIRouter()

# false (по умолчанию): в API код CDEK, выбор ПВЗ, расчёт через СДЭК.
# true — фолбэк CDEK_MANUAL: адрес одной строкой, стоимость доставки в чек не кладётся до согласования.
_CDEK_MANUAL_RAW = (os.getenv("CDEK_PUBLIC_AS_MANUAL_ADDRESS", "false") or "").strip().lower()
CDEK_PUBLIC_AS_MANUAL_ADDRESS = _CDEK_MANUAL_RAW in ("1", "true", "yes", "on")


RequiredField = Literal["address", "phone", "recipient_name", "pickup_point_code"]


class DeliveryMethodPublic(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    code: str
    name: str
    required_fields: List[RequiredField]


def _ensure_default_methods(session: AsyncSession, existing: list[DeliveryMethod]) -> list[DeliveryMethod]:
    """
    Небольшой bootstrap: если таблица пустая, создаём три базовых способа доставки.
    """
    if existing:
        return existing

    methods = [
        DeliveryMethod(
            name="ПВЗ г. Уссурийск",
            # Для ПВЗ из нашего списка адрес не просим у пользователя
            requires_address=False,
            address_not_required=True,
        ),
        DeliveryMethod(
            name="Курьер г. Уссурийск",
            # Курьеру нужен адрес клиента
            requires_address=True,
            address_not_required=False,
        ),
        DeliveryMethod(
            name="CDEK",
            # Адрес ПВЗ приходит из интеграции CDEK, от пользователя нужны ФИО/телефон/ПВЗ
            requires_address=False,
            address_not_required=False,
        ),
    ]
    session.add_all(methods)
    # flush, чтобы появились id
    return methods


def _map_method_to_public(method: DeliveryMethod) -> DeliveryMethodPublic:
    """
    Маппинг 1:1 из модели БД в публичный формат с code/required_fields.

    Чуть захардкожено по name, чтобы было просто и предсказуемо.
    """
    name = (method.name or "").strip()
    display_name = name
    code: str
    required_fields: list[RequiredField]

    if name.startswith("ПВЗ г. Уссурийск"):
        code = "PICKUP_LOCAL"
        required_fields = []
    elif name.startswith("Курьер г. Уссурийск"):
        code = "COURIER_LOCAL"
        required_fields = ["address", "phone"]
    elif name.upper().startswith("CDEK"):
        if CDEK_PUBLIC_AS_MANUAL_ADDRESS:
            code = "CDEK_MANUAL"
            required_fields = ["recipient_name", "phone", "address"]
            display_name = "Доставка СДЭК (адрес вручную)"
        else:
            code = "CDEK"
            required_fields = ["recipient_name", "phone", "pickup_point_code"]
    else:
        # Фолбэк для будущих методов: просим адрес и телефон
        code = f"METHOD_{method.id}"
        required_fields = ["address", "phone"]

    return DeliveryMethodPublic(
        id=method.id,
        code=code,
        name=display_name,
        required_fields=required_fields,
    )


@router.get("/delivery-methods", response_model=List[DeliveryMethodPublic])
async def list_delivery_methods(
    session: AsyncSession = Depends(get_session),
) -> List[DeliveryMethodPublic]:
    """
    Получить список способов доставки, которые доступны пользователю.

    Возвращаем код и список обязательных полей для каждого способа.
    """
    result = await session.execute(select(DeliveryMethod).order_by(DeliveryMethod.id.asc()))
    methods = list(result.scalars().all())

    if not methods:
        methods = _ensure_default_methods(session, methods)
        await session.commit()
        # перечитываем, чтобы были id из БД
        result = await session.execute(select(DeliveryMethod).order_by(DeliveryMethod.id.asc()))
        methods = list(result.scalars().all())

    return [_map_method_to_public(m) for m in methods]

