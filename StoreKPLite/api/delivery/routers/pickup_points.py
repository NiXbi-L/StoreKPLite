"""
Публичный эндпоинт: список ПВЗ СДЭК по городу (код или название), расчёт стоимости для чекаута.
"""
import logging
import os
import re
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.delivery.cdek import (
    cdek_insurance_services,
    get_calculator_tariff,
    get_delivery_points,
    get_tariff_list,
    resolve_city_code,
)
from api.delivery.cdek.tariff_pick import _delivery_sum, _tariff_code, pick_tariff_row
from api.delivery.database.database import get_session
from api.delivery.models.cdek_sender_config import CdekSenderConfig
from api.delivery.models.local_courier_config import LocalCourierConfig

logger = logging.getLogger(__name__)

router = APIRouter()

DeliveryMethodCode = Literal["PICKUP_LOCAL", "COURIER_LOCAL", "CDEK", "CDEK_MANUAL"]


class ParcelBody(BaseModel):
    weight_gram: int = 1000
    length_cm: int = 10
    width_cm: int = 10
    height_cm: int = 10


class CalculateCostRequest(BaseModel):
    parcel: ParcelBody
    delivery_method_code: DeliveryMethodCode
    to_city: Optional[str] = None
    to_city_code: Optional[int] = None
    # Код ПВЗ СДЭК получателя — в калькулятор уходит delivery_point (вместе с shipment_point отправителя из env).
    cdek_delivery_point_code: Optional[str] = None
    # Объявленная стоимость груза (₽) для страховки в POST /calculator/tariff.
    # При CDEK_ADD_INSURANCE_TO_ORDERS=1 в окружении delivery-service страховка считается, если передана только сумма
    # (миниапп); products-service может дополнительно передать cdek_add_insurance=true.
    cdek_declared_value_rub: Optional[float] = None
    cdek_add_insurance: bool = False


class CalculateCostResponse(BaseModel):
    """Ответ расчёта доставки; для CDEK — в т.ч. код тарифа для создания заказа в том же режиме, что в ЛК."""

    delivery_cost_rub: Optional[float]
    cdek_tariff_code: Optional[int] = None
    # При расчёте со страховкой: база доставки и итог по данным POST /calculator/tariff (если СДЭК вернул поля).
    cdek_delivery_sum_base_rub: Optional[float] = None
    cdek_total_sum_rub: Optional[float] = None


def _extract_coords(raw: dict[str, Any], loc: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    """Извлекает lat/lon из location или из других типичных полей ответа СДЭК."""
    for obj in (loc, raw):
        if not isinstance(obj, dict):
            continue
        lat = _get_float(obj, "latitude") or _get_float(obj, "lat")
        lon = _get_float(obj, "longitude") or _get_float(obj, "lng") or _get_float(obj, "lon")
        if lat is not None and lon is not None:
            return lat, lon
        # Вложенный объект coordinates / point / geo
        for key in ("coordinates", "point", "geo"):
            sub = obj.get(key)
            if isinstance(sub, dict):
                la = _get_float(sub, "latitude") or _get_float(sub, "lat") or sub.get("y")
                lo = _get_float(sub, "longitude") or _get_float(sub, "lng") or _get_float(sub, "lon") or sub.get("x")
                if la is not None and lo is not None:
                    try:
                        return float(la), float(lo)
                    except (TypeError, ValueError):
                        pass
    return None, None


def _strip_country_from_address(s: str) -> str:
    """Убирает название страны в начале строки адреса (для сохранения в БД и накладной: край, город, остальное)."""
    if not s or not isinstance(s, str):
        return s or ""
    t = s.strip()
    for prefix in ("Россия, ", "Россия,", "Russia, ", "Russia,"):
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    return t


def _full_address_no_country(loc: dict[str, Any], raw: dict[str, Any]) -> str:
    """
    Полный адрес ПВЗ без страны: край, город и дальше (для накладной и сохранения в БД).
    Собирается из location (region, city, address) или из сырого address с отрезанием страны.
    """
    region = (loc.get("region") or "").strip()
    city = (loc.get("city") or raw.get("city") or "").strip()
    addr_part = (
        loc.get("address")
        or raw.get("address")
        or raw.get("address_comment")
        or raw.get("name")
        or ""
    )
    if isinstance(addr_part, str):
        addr_part = _strip_country_from_address(addr_part).strip()
    else:
        addr_part = ""

    parts = [p for p in (region, city, addr_part) if p]
    if parts:
        return ", ".join(parts)
    raw_addr = (
        loc.get("address")
        or raw.get("address")
        or raw.get("address_comment")
        or raw.get("name")
        or ""
    )
    return _strip_country_from_address(str(raw_addr)) if raw_addr else ""


def _short_address_for_map(loc: dict[str, Any], raw: dict[str, Any], full_address: str) -> str:
    """
    Короткий адрес для подписи на карте: город и улица (без края/области).
    """
    city = (loc.get("city") or raw.get("city") or "").strip()
    addr_part = (
        loc.get("address")
        or raw.get("address")
        or raw.get("address_comment")
        or raw.get("name")
        or ""
    )
    if isinstance(addr_part, str):
        addr_part = _strip_country_from_address(addr_part).strip()
    else:
        addr_part = ""
    if city and addr_part:
        return f"{city}, {addr_part}"
    if addr_part:
        return addr_part
    if city:
        return city
    return full_address


def _normalize_pvz_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Приводит элемент ПВЗ из ответа СДЭК v2 к единому формату для фронта (включая координаты для карт и расчёта)."""
    loc = raw.get("location")
    if isinstance(loc, list) and loc:
        loc = loc[0] if isinstance(loc[0], dict) else {}
    elif not isinstance(loc, dict):
        loc = {}
    address = _full_address_no_country(loc, raw)
    address_short = _short_address_for_map(loc, raw, address)
    lat, lon = _extract_coords(raw, loc)
    cc = loc.get("city_code") or raw.get("city_code")
    try:
        city_code_int = int(cc) if cc is not None and str(cc).strip() != "" else None
    except (TypeError, ValueError):
        city_code_int = None
    return {
        "code": raw.get("code") or raw.get("office_code") or str(raw.get("id", "")),
        "name": raw.get("name", ""),
        "address": address,
        "address_short": address_short,
        "city": loc.get("city") or raw.get("city", ""),
        "city_code": city_code_int,
        "postal_code": loc.get("postal_code") or raw.get("postal_code", ""),
        "lat": lat,
        "lon": lon,
        "work_time": raw.get("work_time") or raw.get("work_time_list") or "",
        "is_dressing_room": raw.get("is_dressing_room", False),
        "is_cash_payment": raw.get("have_cash", raw.get("is_cash_payment", False)),
        "is_card_payment": raw.get("have_cashless", raw.get("is_card_payment", True)),
    }


def _get_float(obj: Any, path: str) -> Optional[float]:
    if not isinstance(obj, dict):
        return None
    if "." in path:
        key, rest = path.split(".", 1)
        val = obj.get(key)
        return _get_float(val, rest) if isinstance(val, dict) else None
    val = obj.get(path)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _pickup_address_match(row: dict[str, Any], address_query: str) -> bool:
    """Подстроки из запроса (разделитель пробел/запятая), минимум 2 символа на токен — все должны встречаться в адресе."""
    q = (address_query or "").strip().lower()
    if not q:
        return True
    hay = f"{row.get('name', '')} {row.get('address', '')} {row.get('address_short', '')} {row.get('city', '')}".lower()
    tokens = [t for t in re.split(r"[\s,;]+", q) if len(t) >= 2]
    if not tokens:
        return q in hay
    return all(t in hay for t in tokens)


@router.get(
    "/pickup-points",
    summary="Список ПВЗ СДЭК",
    description="Возвращает пункты выдачи заказов в заданном городе. Можно передать код города (city_code) или название (city). "
    "Параметр address_query — фильтр по названию/адресу/городу (без карты; улица и дом через подстроки).",
)
async def list_pickup_points(
    city_code: Optional[int] = Query(None, description="Код города СДЭК"),
    city: Optional[str] = Query(None, description="Название города (подстрока); если задано, ищется код города"),
    country_code: str = Query("RU", description="Код страны"),
    address_query: Optional[str] = Query(
        None,
        description="Фильтр по адресу и названию ПВЗ (подстроки через пробел, например «Ленина 15»)",
    ),
    limit: int = Query(50, ge=1, le=500, description="Максимум ПВЗ в ответе после фильтра"),
) -> list[dict[str, Any]]:
    if city_code is None and not (city and city.strip()):
        raise HTTPException(
            status_code=400,
            detail="Укажите city_code (код города СДЭК) или city (название города).",
        )
    if city_code is None:
        resolved = await resolve_city_code(city.strip(), country_code)
        if resolved is None:
            raise HTTPException(
                status_code=404,
                detail=f"Город не найден в справочнике СДЭК: {city!r}",
            )
        city_code = resolved
    try:
        raw_list = await get_delivery_points(city_code)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("CDEK get_delivery_points error: %s", e)
        raise HTTPException(status_code=502, detail="Ошибка при запросе к СДЭК")
    normalized = [_normalize_pvz_item(item) for item in raw_list]
    if address_query and address_query.strip():
        normalized = [row for row in normalized if _pickup_address_match(row, address_query)]
    return normalized[:limit]


@router.get(
    "/delivery-cost",
    summary="Расчёт стоимости доставки между городами",
    description="От кода города отправителя до кода города получателя. Для теста: от ПВЗ MSK65 (Москва, 44) до Уссурийска.",
)
async def delivery_cost(
    from_city_code: int = Query(..., description="Код города СДЭК отправителя (44 = Москва, MSK65)"),
    to_city_code: Optional[int] = Query(None, description="Код города получателя"),
    to_city: Optional[str] = Query(None, description="Название города получателя (если не указан to_city_code)"),
    weight_gram: int = Query(1000, ge=1, le=50000, description="Вес посылки, г"),
    length_cm: int = Query(10, ge=1, le=300),
    width_cm: int = Query(10, ge=1, le=300),
    height_cm: int = Query(10, ge=1, le=300),
) -> dict[str, Any]:
    if to_city_code is None and not (to_city and to_city.strip()):
        raise HTTPException(status_code=400, detail="Укажите to_city_code или to_city")
    if to_city_code is None:
        resolved = await resolve_city_code(to_city.strip(), "RU")
        if resolved is None:
            raise HTTPException(status_code=404, detail=f"Город не найден: {to_city!r}")
        to_city_code = resolved
    try:
        tariffs = await get_tariff_list(
            from_city_code=from_city_code,
            to_city_code=to_city_code,
            weight_gram=weight_gram,
            length_cm=length_cm,
            width_cm=width_cm,
            height_cm=height_cm,
            shipment_point="",
        )
    except Exception as e:
        logger.exception("CDEK get_tariff_list error: %s", e)
        raise HTTPException(status_code=502, detail="Ошибка расчёта стоимости СДЭК")
    if not tariffs:
        return {
            "from_city_code": from_city_code,
            "to_city_code": to_city_code,
            "delivery_sum": None,
            "currency": "RUB",
            "tariff_code": None,
            "message": "Нет доступных тарифов на направление",
        }
    picked = pick_tariff_row(tariffs) or {}
    delivery_sum = _delivery_sum(picked) if picked else None
    if delivery_sum is None and picked:
        delivery_sum = picked.get("delivery_sum") or picked.get("sum") or picked.get("total_sum")
    return {
        "from_city_code": from_city_code,
        "to_city_code": to_city_code,
        "delivery_sum": delivery_sum,
        "currency": picked.get("currency", "RUB") if picked else "RUB",
        "tariff_code": _tariff_code(picked) if picked else None,
    }


@router.post("/calculate-cost", response_model=CalculateCostResponse)
async def calculate_delivery_cost_checkout(
    request: CalculateCostRequest,
    session: AsyncSession = Depends(get_session),
) -> CalculateCostResponse:
    """
    Перерасчёт стоимости доставки для чекаута.
    PICKUP_LOCAL (ПВЗ г. Уссурийск) — 0.
    COURIER_LOCAL (Курьер г. Уссурийск) — цена из настроек админки.
    CDEK_MANUAL — фолбэк без ЛК СДЭК: сумма доставки неизвестна до согласования с менеджером (null, не в чек).
    CDEK — расчёт через калькулятор СДЭК: город отправителя из настроек, ПВЗ отгрузки из CDEK_SENDER_SHIPMENT_POINT
    (по умолчанию USS3), город получателя; при передаче cdek_delivery_point_code — ещё и ПВЗ получателя.
    При ``cdek_add_insurance=true`` и ``cdek_declared_value_rub`` > 0 после выбора тарифа вызывается
    POST /calculator/tariff с услугой INSURANCE; в ответе ``delivery_cost_rub`` = ``total_sum`` (доставка + страховка),
    детализация в ``cdek_delivery_sum_base_rub`` / ``cdek_total_sum_rub``.
    """
    code = request.delivery_method_code
    p = request.parcel

    if code == "PICKUP_LOCAL":
        return CalculateCostResponse(delivery_cost_rub=0.0, cdek_tariff_code=None)

    if code == "COURIER_LOCAL":
        result = await session.execute(select(LocalCourierConfig).limit(1))
        config = result.scalar_one_or_none()
        price = float(config.price_rub) if config and config.price_rub is not None else 0.0
        return CalculateCostResponse(delivery_cost_rub=price, cdek_tariff_code=None)

    if code == "CDEK_MANUAL":
        return CalculateCostResponse(delivery_cost_rub=None, cdek_tariff_code=None)

    if code == "CDEK":
        result = await session.execute(select(CdekSenderConfig).limit(1))
        sender_row = result.scalar_one_or_none()
        from_city_name = (sender_row.city_name if sender_row else "Уссурийск") or "Уссурийск"
        from_city_code = await resolve_city_code(from_city_name.strip(), "RU")
        if from_city_code is None:
            logger.warning("CDEK sender city not resolved: %s", from_city_name)
            return CalculateCostResponse(delivery_cost_rub=None, cdek_tariff_code=None)

        to_city_code = request.to_city_code
        if to_city_code is None and request.to_city and request.to_city.strip():
            to_city_code = await resolve_city_code(request.to_city.strip(), "RU")
            if to_city_code is None and "," in request.to_city:
                parts = [p.strip() for p in request.to_city.split(",") if p.strip()]
                for part in parts[1:2]:
                    if part and len(part) > 2:
                        to_city_code = await resolve_city_code(part, "RU")
                        if to_city_code is not None:
                            break
        if to_city_code is None:
            return CalculateCostResponse(delivery_cost_rub=None, cdek_tariff_code=None)

        dp_calc = (request.cdek_delivery_point_code or "").strip() or None
        try:
            tariffs = await get_tariff_list(
                from_city_code=from_city_code,
                to_city_code=to_city_code,
                weight_gram=p.weight_gram,
                length_cm=p.length_cm,
                width_cm=p.width_cm,
                height_cm=p.height_cm,
                shipment_point=None,
                delivery_point=dp_calc,
            )
        except Exception as e:
            logger.exception("CDEK get_tariff_list error: %s", e)
            return CalculateCostResponse(delivery_cost_rub=None, cdek_tariff_code=None)

        if not tariffs:
            return CalculateCostResponse(delivery_cost_rub=None, cdek_tariff_code=None)
        picked = pick_tariff_row(tariffs, destination_is_pickup_point=bool(dp_calc))
        if not picked:
            return CalculateCostResponse(delivery_cost_rub=None, cdek_tariff_code=None)
        tc = _tariff_code(picked)
        delivery_sum = _delivery_sum(picked)
        if delivery_sum is None:
            delivery_sum = picked.get("delivery_sum") or picked.get("sum") or picked.get("total_sum")

        base_rub: Optional[float] = None
        total_rub: Optional[float] = None
        _env_insurance = (os.getenv("CDEK_ADD_INSURANCE_TO_ORDERS") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        _declared = float(request.cdek_declared_value_rub or 0.0)
        _apply_insurance = _declared > 0 and (_env_insurance or request.cdek_add_insurance)
        ins_sv = cdek_insurance_services(_declared)
        if _apply_insurance and ins_sv and tc is not None:
            try:
                trow = await get_calculator_tariff(
                    from_city_code=from_city_code,
                    to_city_code=to_city_code,
                    tariff_code=int(tc),
                    weight_gram=p.weight_gram,
                    length_cm=p.length_cm,
                    width_cm=p.width_cm,
                    height_cm=p.height_cm,
                    shipment_point=None,
                    delivery_point=dp_calc,
                    services=ins_sv,
                )
                for key in ("delivery_sum", "total_sum"):
                    raw = trow.get(key)
                    if raw is not None:
                        try:
                            v = float(raw)
                        except (TypeError, ValueError):
                            continue
                        if key == "delivery_sum":
                            base_rub = v
                        else:
                            total_rub = v
            except Exception as e:
                logger.warning("CDEK POST /calculator/tariff (страхование): %s", e)

        if total_rub is not None:
            return CalculateCostResponse(
                delivery_cost_rub=total_rub,
                cdek_tariff_code=tc,
                cdek_delivery_sum_base_rub=base_rub,
                cdek_total_sum_rub=total_rub,
            )
        if delivery_sum is not None:
            cost = float(delivery_sum) if isinstance(delivery_sum, (int, float, Decimal)) else None
            return CalculateCostResponse(
                delivery_cost_rub=cost,
                cdek_tariff_code=tc,
            )
        return CalculateCostResponse(delivery_cost_rub=None, cdek_tariff_code=tc)

    return CalculateCostResponse(delivery_cost_rub=None, cdek_tariff_code=None)
