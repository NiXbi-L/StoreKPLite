"""
Админские эндпоинты для локальных ПВЗ и цены курьерской доставки по городу.

Используются из React‑админки через JWT админа.

Имя модуля не local_settings.py: в .gitignore было правило на это имя (чужой шаблон), из‑за него файл не коммитился.
"""
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, condecimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.delivery.database.database import get_session
from api.delivery.models.local_pickup_point import LocalPickupPoint
from api.delivery.models.local_courier_config import LocalCourierConfig
from api.delivery.models.cdek_sender_config import CdekSenderConfig
from api.shared.auth import require_admin_type


router = APIRouter()
require_admin = require_admin_type("admin")


class LocalPickupPointResponse(BaseModel):
  id: int
  city: str
  address: str
  is_active: bool

  class Config:
    from_attributes = True


class LocalPickupPointCreateUpdate(BaseModel):
  city: str
  address: str
  is_active: bool = True


class LocalCourierConfigResponse(BaseModel):
  city: str
  price_rub: Optional[condecimal(max_digits=10, decimal_places=2)] = None

  class Config:
    from_attributes = True


class LocalCourierConfigUpdate(BaseModel):
  city: str
  price_rub: Optional[condecimal(max_digits=10, decimal_places=2)] = None


class CdekSenderConfigResponse(BaseModel):
  city_name: str

  class Config:
    from_attributes = True


class CdekSenderConfigUpdate(BaseModel):
  city_name: str


@router.get("/admin/cdek-sender-config", response_model=CdekSenderConfigResponse)
async def get_cdek_sender_config(
  admin=Depends(require_admin),
  session: AsyncSession = Depends(get_session),
) -> CdekSenderConfigResponse:
  result = await session.execute(select(CdekSenderConfig).limit(1))
  config = result.scalar_one_or_none()
  if not config:
    config = CdekSenderConfig(city_name="Уссурийск")
    session.add(config)
    await session.commit()
    await session.refresh(config)
  return CdekSenderConfigResponse(city_name=config.city_name)


@router.put("/admin/cdek-sender-config", response_model=CdekSenderConfigResponse)
async def update_cdek_sender_config(
  request: CdekSenderConfigUpdate,
  admin=Depends(require_admin),
  session: AsyncSession = Depends(get_session),
) -> CdekSenderConfigResponse:
  result = await session.execute(select(CdekSenderConfig).limit(1))
  config = result.scalar_one_or_none()
  if not config:
    config = CdekSenderConfig(city_name=request.city_name.strip())
    session.add(config)
  else:
    config.city_name = request.city_name.strip()
  await session.commit()
  await session.refresh(config)
  return CdekSenderConfigResponse(city_name=config.city_name)


@router.get("/admin/local-pickup-points", response_model=List[LocalPickupPointResponse])
async def list_local_pickup_points_admin(
  admin=Depends(require_admin),
  session: AsyncSession = Depends(get_session),
) -> List[LocalPickupPointResponse]:
  result = await session.execute(
    select(LocalPickupPoint).order_by(LocalPickupPoint.created_at.asc())
  )
  return list(result.scalars().all())


@router.get("/local-pickup-points", response_model=List[LocalPickupPointResponse])
async def list_local_pickup_points_public(
  session: AsyncSession = Depends(get_session),
) -> List[LocalPickupPointResponse]:
  """
  Публичный эндпоинт для миниапки: активные ПВЗ (без авторизации админа).
  """
  result = await session.execute(
    select(LocalPickupPoint)
    .where(LocalPickupPoint.is_active.is_(True))
    .order_by(LocalPickupPoint.created_at.asc())
  )
  return list(result.scalars().all())


@router.post("/admin/local-pickup-points", response_model=LocalPickupPointResponse)
async def create_local_pickup_point(
  request: LocalPickupPointCreateUpdate,
  admin=Depends(require_admin),
  session: AsyncSession = Depends(get_session),
) -> LocalPickupPointResponse:
  point = LocalPickupPoint(
    city=request.city.strip(),
    address=request.address.strip(),
    is_active=request.is_active,
  )
  session.add(point)
  await session.commit()
  await session.refresh(point)
  return point


@router.put("/admin/local-pickup-points/{point_id}", response_model=LocalPickupPointResponse)
async def update_local_pickup_point(
  point_id: int,
  request: LocalPickupPointCreateUpdate,
  admin=Depends(require_admin),
  session: AsyncSession = Depends(get_session),
) -> LocalPickupPointResponse:
  result = await session.execute(
    select(LocalPickupPoint).where(LocalPickupPoint.id == point_id)
  )
  point = result.scalar_one_or_none()
  if not point:
    raise HTTPException(status_code=404, detail="ПВЗ не найден")

  point.city = request.city.strip()
  point.address = request.address.strip()
  point.is_active = request.is_active

  await session.commit()
  await session.refresh(point)
  return point


@router.delete("/admin/local-pickup-points/{point_id}")
async def delete_local_pickup_point(
  point_id: int,
  admin=Depends(require_admin),
  session: AsyncSession = Depends(get_session),
):
  result = await session.execute(
    select(LocalPickupPoint).where(LocalPickupPoint.id == point_id)
  )
  point = result.scalar_one_or_none()
  if not point:
    raise HTTPException(status_code=404, detail="ПВЗ не найден")

  await session.delete(point)
  await session.commit()
  return {"detail": "ПВЗ удалён"}


@router.get("/admin/local-courier-config", response_model=LocalCourierConfigResponse)
async def get_local_courier_config(
  admin=Depends(require_admin),
  session: AsyncSession = Depends(get_session),
) -> LocalCourierConfigResponse:
  result = await session.execute(select(LocalCourierConfig).limit(1))
  config = result.scalar_one_or_none()
  if not config:
    # Конфиг по умолчанию для Уссурийска без цены
    config = LocalCourierConfig(city="Уссурийск", price_rub=None)
    session.add(config)
    await session.commit()
    await session.refresh(config)

  return LocalCourierConfigResponse(
    city=config.city,
    price_rub=Decimal(config.price_rub) if config.price_rub is not None else None,
  )


@router.put("/admin/local-courier-config", response_model=LocalCourierConfigResponse)
async def update_local_courier_config(
  request: LocalCourierConfigUpdate,
  admin=Depends(require_admin),
  session: AsyncSession = Depends(get_session),
) -> LocalCourierConfigResponse:
  result = await session.execute(select(LocalCourierConfig).limit(1))
  config = result.scalar_one_or_none()
  if not config:
    config = LocalCourierConfig(city=request.city.strip(), price_rub=None)
    session.add(config)
  else:
    config.city = request.city.strip()

  if request.price_rub is not None:
    config.price_rub = Decimal(request.price_rub)
  else:
    config.price_rub = None

  await session.commit()
  await session.refresh(config)

  return LocalCourierConfigResponse(
    city=config.city,
    price_rub=Decimal(config.price_rub) if config.price_rub is not None else None,
  )
