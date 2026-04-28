"""
Роутер для настроек финансов
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
import httpx
import logging
from os import getenv

from api.finance.database.database import get_session
from api.finance.models.finance_settings import FinanceSettings
from api.finance.models.exchange_rate import ExchangeRate
from api.shared.auth import verify_jwt_token
from api.finance.utils.exchange_rate_loader import load_exchange_rate

logger = logging.getLogger(__name__)

router = APIRouter()

PRODUCTS_SERVICE_URL = getenv("PRODUCTS_SERVICE_URL", "http://products-service:8002")
INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")

async def require_owner_admin(payload: dict = Depends(verify_jwt_token)) -> dict:
    if (payload.get("admin_type") or "").strip().lower() != "owner":
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return payload


class FinanceSettingsResponse(BaseModel):
    depreciation_percent: float
    working_capital_limit: Optional[float]
    delivery_cost_per_kg: Optional[float]
    exchange_rate_margin_percent: float
    yuan_markup_before_rub_percent: float
    customer_price_acquiring_factor: float
    tryon_unit_price_rub: Optional[float] = None
    tryon_max_discount_units_per_item: int = 3
    tryon_generation_internal_cost_rub: Optional[float] = None
    tryon_clothing_profit_to_api_reserve_percent: Optional[float] = None

    class Config:
        from_attributes = True


class UpdateFinanceSettingsRequest(BaseModel):
    depreciation_percent: float
    working_capital_limit: Optional[float] = None
    delivery_cost_per_kg: Optional[float] = None
    exchange_rate_margin_percent: float
    yuan_markup_before_rub_percent: float = 0
    customer_price_acquiring_factor: float = 0.97
    tryon_unit_price_rub: Optional[float] = None
    tryon_max_discount_units_per_item: Optional[int] = None
    tryon_generation_internal_cost_rub: Optional[float] = None
    tryon_clothing_profit_to_api_reserve_percent: Optional[float] = None


@router.get("/settings/delivery-cost")
async def get_delivery_cost(
    session: AsyncSession = Depends(get_session)
):
    """Получить стоимость доставки за кг (публичный endpoint для других сервисов)"""
    
    result = await session.execute(select(FinanceSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        return {"delivery_cost_per_kg": None}
    
    return {
        "delivery_cost_per_kg": float(settings.delivery_cost_per_kg) if settings.delivery_cost_per_kg else None
    }


@router.get("/internal/price-context")
async def get_price_context(
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    """
    Объединённый endpoint: курс CNY (rate_with_margin) и стоимость доставки за кг.
    Только межсервисно (X-Internal-Token).
    """
    if not x_internal_token or x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный внутренний токен")
    rate_result = await session.execute(select(ExchangeRate).where(ExchangeRate.currency_code == "CNY"))
    settings_result = await session.execute(select(FinanceSettings).limit(1))
    exchange_rate = rate_result.scalar_one_or_none()
    settings = settings_result.scalar_one_or_none()
    rate_with_margin = float(exchange_rate.rate_with_margin) if exchange_rate else 12.5
    delivery_cost_per_kg = None
    if settings and settings.delivery_cost_per_kg is not None:
        delivery_cost_per_kg = float(settings.delivery_cost_per_kg)
    yuan_pct = float(getattr(settings, "yuan_markup_before_rub_percent", 0) or 0) if settings else 0.0
    acq = float(getattr(settings, "customer_price_acquiring_factor", 0.97) or 0.97) if settings else 0.97
    return {
        "rate_with_margin": rate_with_margin,
        "delivery_cost_per_kg": delivery_cost_per_kg,
        "yuan_markup_before_rub_percent": yuan_pct,
        "customer_price_acquiring_factor": acq,
    }


@router.get("/admin/settings", response_model=FinanceSettingsResponse)
async def get_finance_settings(
    admin = Depends(require_owner_admin),
    session: AsyncSession = Depends(get_session)
):
    """Получить настройки финансов (для админов)"""
    result = await session.execute(select(FinanceSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        # Создаем настройки по умолчанию
        settings = FinanceSettings(
            depreciation_percent=Decimal("3.00"),
            working_capital_limit=None,
            delivery_cost_per_kg=None,
            exchange_rate_margin_percent=Decimal("10.00"),
            yuan_markup_before_rub_percent=Decimal("0"),
            customer_price_acquiring_factor=Decimal("0.97"),
            tryon_unit_price_rub=None,
            tryon_max_discount_units_per_item=3,
            tryon_generation_internal_cost_rub=Decimal("20"),
            tryon_clothing_profit_to_api_reserve_percent=None,
        )
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    
    return FinanceSettingsResponse(
        depreciation_percent=float(settings.depreciation_percent),
        working_capital_limit=float(settings.working_capital_limit) if settings.working_capital_limit else None,
        delivery_cost_per_kg=float(settings.delivery_cost_per_kg) if settings.delivery_cost_per_kg else None,
        exchange_rate_margin_percent=float(settings.exchange_rate_margin_percent),
        yuan_markup_before_rub_percent=float(getattr(settings, "yuan_markup_before_rub_percent", 0) or 0),
        customer_price_acquiring_factor=float(getattr(settings, "customer_price_acquiring_factor", 0.97) or 0.97),
        tryon_unit_price_rub=float(settings.tryon_unit_price_rub) if settings.tryon_unit_price_rub is not None else None,
        tryon_max_discount_units_per_item=int(getattr(settings, "tryon_max_discount_units_per_item", None) or 3),
        tryon_generation_internal_cost_rub=float(settings.tryon_generation_internal_cost_rub)
        if getattr(settings, "tryon_generation_internal_cost_rub", None) is not None
        else None,
        tryon_clothing_profit_to_api_reserve_percent=float(settings.tryon_clothing_profit_to_api_reserve_percent)
        if getattr(settings, "tryon_clothing_profit_to_api_reserve_percent", None) is not None
        else None,
    )


@router.put("/admin/settings", response_model=FinanceSettingsResponse)
async def update_finance_settings(
    request: UpdateFinanceSettingsRequest,
    admin = Depends(require_owner_admin),
    session: AsyncSession = Depends(get_session)
):
    """Обновить настройки финансов (для админов)"""
    if request.depreciation_percent < 0 or request.depreciation_percent > 100:
        raise HTTPException(status_code=400, detail="Процент амортизации должен быть от 0 до 100")
    if request.tryon_unit_price_rub is not None:
        if request.tryon_unit_price_rub < 0:
            raise HTTPException(status_code=400, detail="Цена примерки не может быть отрицательной")
        if 0 < request.tryon_unit_price_rub < 0.01:
            raise HTTPException(status_code=400, detail="Минимальная цена примерки: 0.01 ₽")
    if request.tryon_max_discount_units_per_item is not None:
        if request.tryon_max_discount_units_per_item < 1 or request.tryon_max_discount_units_per_item > 100:
            raise HTTPException(
                status_code=400,
                detail="tryon_max_discount_units_per_item должен быть от 1 до 100",
            )
    if request.yuan_markup_before_rub_percent < 0 or request.yuan_markup_before_rub_percent > 500:
        raise HTTPException(status_code=400, detail="yuan_markup_before_rub_percent: 0–500")
    if request.customer_price_acquiring_factor <= 0 or request.customer_price_acquiring_factor > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "customer_price_acquiring_factor — доля «остаётся после эквайринга» (0, 1], например 0.97; "
                "цена клиента = (база+доставка+сбор) / это значение"
            ),
        )
    if request.tryon_generation_internal_cost_rub is not None and request.tryon_generation_internal_cost_rub < 0:
        raise HTTPException(status_code=400, detail="Учётная себестоимость примерки не может быть отрицательной")
    if request.tryon_clothing_profit_to_api_reserve_percent is not None:
        p = request.tryon_clothing_profit_to_api_reserve_percent
        if p < 0 or p > 100:
            raise HTTPException(
                status_code=400,
                detail="tryon_clothing_profit_to_api_reserve_percent: от 0 до 100",
            )

    result = await session.execute(select(FinanceSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    old_delivery_cost = None
    old_margin_percent = None
    old_yuan_markup = None
    old_acquiring = None

    if not settings:
        settings = FinanceSettings(
            depreciation_percent=Decimal(str(request.depreciation_percent)),
            working_capital_limit=Decimal(str(request.working_capital_limit)) if request.working_capital_limit else None,
            delivery_cost_per_kg=Decimal(str(request.delivery_cost_per_kg)) if request.delivery_cost_per_kg else None,
            exchange_rate_margin_percent=Decimal(str(request.exchange_rate_margin_percent)),
            yuan_markup_before_rub_percent=Decimal(str(request.yuan_markup_before_rub_percent)),
            customer_price_acquiring_factor=Decimal(str(request.customer_price_acquiring_factor)),
            tryon_unit_price_rub=Decimal(str(request.tryon_unit_price_rub)) if request.tryon_unit_price_rub is not None else None,
            tryon_max_discount_units_per_item=request.tryon_max_discount_units_per_item or 3,
            tryon_generation_internal_cost_rub=Decimal(str(request.tryon_generation_internal_cost_rub))
            if request.tryon_generation_internal_cost_rub is not None
            else Decimal("20"),
            tryon_clothing_profit_to_api_reserve_percent=Decimal(str(request.tryon_clothing_profit_to_api_reserve_percent))
            if request.tryon_clothing_profit_to_api_reserve_percent is not None
            else None,
        )
        session.add(settings)
    else:
        old_delivery_cost = settings.delivery_cost_per_kg
        old_margin_percent = settings.exchange_rate_margin_percent
        old_yuan_markup = getattr(settings, "yuan_markup_before_rub_percent", None)
        old_acquiring = getattr(settings, "customer_price_acquiring_factor", None)

        settings.depreciation_percent = Decimal(str(request.depreciation_percent))
        settings.working_capital_limit = Decimal(str(request.working_capital_limit)) if request.working_capital_limit else None
        settings.delivery_cost_per_kg = Decimal(str(request.delivery_cost_per_kg)) if request.delivery_cost_per_kg else None
        settings.exchange_rate_margin_percent = Decimal(str(request.exchange_rate_margin_percent))
        settings.yuan_markup_before_rub_percent = Decimal(str(request.yuan_markup_before_rub_percent))
        settings.customer_price_acquiring_factor = Decimal(str(request.customer_price_acquiring_factor))
        if request.tryon_unit_price_rub is not None:
            settings.tryon_unit_price_rub = Decimal(str(request.tryon_unit_price_rub))
        else:
            settings.tryon_unit_price_rub = None
        if request.tryon_max_discount_units_per_item is not None:
            settings.tryon_max_discount_units_per_item = int(request.tryon_max_discount_units_per_item)
        if request.tryon_generation_internal_cost_rub is not None:
            settings.tryon_generation_internal_cost_rub = Decimal(str(request.tryon_generation_internal_cost_rub))
        else:
            if getattr(settings, "tryon_generation_internal_cost_rub", None) is None:
                settings.tryon_generation_internal_cost_rub = Decimal("20")
        if request.tryon_clothing_profit_to_api_reserve_percent is not None:
            settings.tryon_clothing_profit_to_api_reserve_percent = Decimal(
                str(request.tryon_clothing_profit_to_api_reserve_percent)
            )

    await session.commit()
    await session.refresh(settings)
    
    # Если изменились параметры, влияющие на цену витрины, обновляем историю цен всех товаров
    # и при смене наценки на курс пересчитываем курс
    price_shape_changed = (
        old_delivery_cost != settings.delivery_cost_per_kg
        or old_margin_percent != settings.exchange_rate_margin_percent
        or old_yuan_markup != settings.yuan_markup_before_rub_percent
        or old_acquiring != settings.customer_price_acquiring_factor
    )
    if price_shape_changed:
        # Если изменилась наценка на курс, пересчитываем курс
        if old_margin_percent != settings.exchange_rate_margin_percent:
            try:
                await load_exchange_rate(session)
                logger.info("Курс валют пересчитан с новой наценкой")
            except Exception as e:
                logger.error(f"Ошибка при пересчете курса: {e}", exc_info=True)
        
        # Уведомляем products-service о необходимости пересчитать историю цен
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{PRODUCTS_SERVICE_URL}/internal/recalculate-price-history",
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    timeout=60.0  # Может занять время для всех товаров
                )
                if response.status_code == 200:
                    logger.info("История цен всех товаров обновлена")
                else:
                    logger.warning(f"Не удалось пересчитать историю цен: {response.status_code}")
        except Exception as e:
            logger.error(f"Ошибка при уведомлении products-service о пересчете истории цен: {e}")
    
    return FinanceSettingsResponse(
        depreciation_percent=float(settings.depreciation_percent),
        working_capital_limit=float(settings.working_capital_limit) if settings.working_capital_limit else None,
        delivery_cost_per_kg=float(settings.delivery_cost_per_kg) if settings.delivery_cost_per_kg else None,
        exchange_rate_margin_percent=float(settings.exchange_rate_margin_percent),
        yuan_markup_before_rub_percent=float(settings.yuan_markup_before_rub_percent),
        customer_price_acquiring_factor=float(settings.customer_price_acquiring_factor),
        tryon_unit_price_rub=float(settings.tryon_unit_price_rub) if settings.tryon_unit_price_rub is not None else None,
        tryon_max_discount_units_per_item=int(getattr(settings, "tryon_max_discount_units_per_item", None) or 3),
        tryon_generation_internal_cost_rub=float(settings.tryon_generation_internal_cost_rub)
        if getattr(settings, "tryon_generation_internal_cost_rub", None) is not None
        else None,
        tryon_clothing_profit_to_api_reserve_percent=float(settings.tryon_clothing_profit_to_api_reserve_percent)
        if getattr(settings, "tryon_clothing_profit_to_api_reserve_percent", None) is not None
        else None,
    )

