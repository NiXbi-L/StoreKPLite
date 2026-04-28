"""
Клиент API СДЭК v2: OAuth-токен и получение списка ПВЗ.
Документация: https://apidoc.cdek.ru/

Отладка исходящих JSON в СДЭК: CDEK_DEBUG_LOG_REQUEST_BODIES=1 (и опционально CDEK_DEBUG_LOG_REQUEST_BODY_MAX).
Перед продом выключить флаг или убрать вызовы — в лог попадают персональные данные получателя.
"""
import json
import logging
import os
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Доп. услуга «страхование груза» в API СДЭК v2 (см. справочник услуг и POST /calculator/tariff в официальной документации).
CDEK_SERVICE_CODE_INSURANCE = "INSURANCE"


def cdek_insurance_services(declared_value_rub: float) -> list[dict[str, Any]]:
    """Один элемент services для калькулятора / заказа: parameter — страховая (объявленная) сумма, ₽."""
    v = float(declared_value_rub)
    if v <= 0:
        return []
    return [{"code": CDEK_SERVICE_CODE_INSURANCE, "parameter": round(v, 2)}]


def _cdek_debug_log_bodies_enabled() -> bool:
    return (os.getenv("CDEK_DEBUG_LOG_REQUEST_BODIES") or "").strip().lower() in ("1", "true", "yes", "on")


def log_cdek_debug_request_body(context: str, body: Any) -> None:
    """
    Логирует тело исходящего запроса в СДЭК (JSON). Только при CDEK_DEBUG_LOG_REQUEST_BODIES=1.
    Не логирует OAuth (client_secret) — вызывать только для /calculator/*, /orders и т.п.
    """
    if not _cdek_debug_log_bodies_enabled():
        return
    try:
        s = json.dumps(body, ensure_ascii=False, default=str)
    except Exception:
        s = repr(body)
    try:
        max_len = int((os.getenv("CDEK_DEBUG_LOG_REQUEST_BODY_MAX") or "32768").strip())
    except ValueError:
        max_len = 32768
    max_len = max(4096, min(max_len, 262144))
    if len(s) > max_len:
        s = s[:max_len] + "...[truncated]"
    logger.info("CDEK outbound JSON %s: %s", context, s)

# Кэш токена: (token, expires_at_timestamp)
_token_cache: tuple[str, float] = ("", 0.0)
# Запас времени до истечения (секунды), чтобы обновить токен заранее
_TOKEN_BUFFER_SEC = 60


def _get_config() -> tuple[str, str, str]:
    base = os.getenv("CDEK_API_BASE_URL", "https://api.edu.cdek.ru/v2").rstrip("/")
    account = os.getenv("CDEK_ACCOUNT", "")
    secret = os.getenv("CDEK_SECRET", "")
    return base, account, secret


async def _fetch_token(base_url: str, account: str, secret: str) -> tuple[str, int]:
    """POST oauth/token, возвращает (access_token, expires_in)."""
    url = f"{base_url}/oauth/token"
    # СДЭК ожидает application/x-www-form-urlencoded, OAuth2 client_credentials
    data = {
        "grant_type": "client_credentials",
        "client_id": account,
        "client_secret": secret,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        body = resp.json()
    token = body.get("access_token") or ""
    expires_in = int(body.get("expires_in", 3600))
    if not token:
        raise ValueError("CDEK API: в ответе oauth/token нет access_token")
    return token, expires_in


def _get_cached_token() -> Optional[str]:
    global _token_cache
    token, expires_at = _token_cache
    if token and time.time() < (expires_at - _TOKEN_BUFFER_SEC):
        return token
    return None


def _set_cached_token(token: str, expires_in: int) -> None:
    global _token_cache
    _token_cache = (token, time.time() + expires_in)


async def get_cdek_token() -> str:
    """Возвращает актуальный access_token (из кэша или новый запрос)."""
    cached = _get_cached_token()
    if cached:
        return cached
    base_url, account, secret = _get_config()
    if not account or not secret:
        raise ValueError("CDEK_ACCOUNT и CDEK_SECRET должны быть заданы в окружении")
    token, expires_in = await _fetch_token(base_url, account, secret)
    _set_cached_token(token, expires_in)
    logger.debug("CDEK: получен новый access_token, expires_in=%s", expires_in)
    return token


def _parse_deliverypoints_response(data: Any) -> list[dict[str, Any]]:
    """Из ответа СДЭК извлекает список ПВЗ (список или обёрнутый в объект)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "deliverypoints" in data:
            return data["deliverypoints"] if isinstance(data["deliverypoints"], list) else []
        if "data" in data:
            return data["data"] if isinstance(data["data"], list) else []
    return []


async def get_delivery_points(
    city_code: int,
    size: int = 1000,
    fetch_all_pages: bool = True,
) -> list[dict[str, Any]]:
    """
    Список ПВЗ СДЭК в заданном городе (код города в системе СДЭК).
    size — макс. пунктов за один запрос (по умолчанию 1000).
    Если fetch_all_pages=True, запрашиваются все страницы (page=0,1,...), пока не вернётся меньше size.
    """
    base_url, _, _ = _get_config()
    token = await get_cdek_token()
    url = f"{base_url}/deliverypoints"
    headers = {"Authorization": f"Bearer {token}"}
    result: list[dict[str, Any]] = []
    page = 0
    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            params: dict[str, Any] = {"city_code": city_code, "size": size, "page": page}
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            chunk = _parse_deliverypoints_response(data)
            result.extend(chunk)
            if not fetch_all_pages or len(chunk) < size:
                break
            page += 1
    return result


async def get_cities(
    country_code: str = "RU",
    city_name: Optional[str] = None,
    size: int = 30,
) -> list[dict[str, Any]]:
    """
    Список городов СДЭК. Если задан city_name — поиск по названию (подстрока).
    """
    base_url, _, _ = _get_config()
    token = await get_cdek_token()
    url = f"{base_url}/location/cities"
    params: dict[str, Any] = {"country_codes": country_code, "size": size}
    if city_name:
        params["city"] = city_name.strip()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "data" in data:
            return data["data"] if isinstance(data["data"], list) else []
        if "cities" in data:
            return data["cities"] if isinstance(data["cities"], list) else []
    return []


async def resolve_city_code(city_name: str, country_code: str = "RU") -> Optional[int]:
    """
    По названию города возвращает код города СДЭК (первое совпадение).
    """
    cities = await get_cities(country_code=country_code, city_name=city_name, size=5)
    for c in cities:
        code = c.get("code")
        if code is not None:
            return int(code) if isinstance(code, (int, float)) else None
    return None


async def get_tariff_list(
    from_city_code: int,
    to_city_code: int,
    weight_gram: int = 1000,
    length_cm: int = 10,
    width_cm: int = 10,
    height_cm: int = 10,
    *,
    shipment_point: Optional[str] = None,
    delivery_point: Optional[str] = None,
    services: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """
    Расчёт стоимости доставки между городами (коды СДЭК).
    Возвращает список тарифов с полями delivery_sum, tariff_code и т.д.
    Вес в граммах.

    shipment_point: код ПВЗ отгрузки в POST /calculator/tarifflist (как в заказе). None — взять из
    CDEK_SENDER_SHIPMENT_POINT (по умолчанию USS3). Пустая строка — не передавать в теле (для тестовых вызовов).
    delivery_point: код ПВЗ получателя, если известен (ПВЗ–ПВЗ).

    На api.cdek.ru (прод) калькулятор ожидает непустые from_location и to_location (код города),
    иначе v2_field_is_empty — даже если заданы shipment_point и delivery_point. Это отличается от
    ограничений POST /orders (там нельзя смешивать to_location с delivery_point).

    services: опционально список доп. услуг (как в POST /calculator/tariff), например страхование —
    ``[{"code": "INSURANCE", "parameter": <сумма в ₽>}]``. Поддержка в tarifflist зависит от версии API;
    для гарантированной суммы с услугами используйте ``get_calculator_tariff`` по уже выбранному ``tariff_code``.
    """
    base_url, _, _ = _get_config()
    token = await get_cdek_token()
    url = f"{base_url}/calculator/tarifflist"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    packages = [
        {
            "weight": int(weight_gram),
            "length": int(length_cm),
            "width": int(width_cm),
            "height": int(height_cm),
        }
    ]
    # lang: в SDK СДЭК (BaseTypes\Tarifflist) — rus | eng | zho; влияет на tariff_name в ответе.
    _lang = (os.getenv("CDEK_TARIFFLIST_LANG") or "rus").strip().lower()
    if _lang not in ("rus", "eng", "zho"):
        _lang = "rus"
    if shipment_point is None:
        sp = os.getenv("CDEK_SENDER_SHIPMENT_POINT", "USS3").strip() or None
    else:
        sp = shipment_point.strip() or None
    dp = (delivery_point or "").strip() or None

    body: dict[str, Any] = {
        "type": 1,
        "lang": _lang,
        "packages": packages,
        # Прод СДЭК: без городов калькулятор отдаёт 400 «[from_location]/[to_location] is empty».
        "from_location": {"code": int(from_city_code)},
        "to_location": {"code": int(to_city_code)},
    }
    if dp:
        body["delivery_point"] = dp
    if sp:
        body["shipment_point"] = sp
    if services:
        body["services"] = services

    log_cdek_debug_request_body("POST /calculator/tarifflist (primary)", body)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=body, headers=headers)
        if resp.status_code == 400 and sp:
            err_txt = (resp.text or "")[:900]
            logger.warning(
                "CDEK POST /calculator/tarifflist 400 (shipment_point=%s), повтор с from_location code=%s: %s",
                sp,
                from_city_code,
                err_txt,
            )
            body_fb = {k: v for k, v in body.items() if k != "shipment_point"}
            body_fb.setdefault("from_location", {"code": int(from_city_code)})
            body_fb.setdefault("to_location", {"code": int(to_city_code)})
            log_cdek_debug_request_body("POST /calculator/tarifflist (fallback from_location)", body_fb)
            resp = await client.post(url, json=body_fb, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "CDEK POST /calculator/tarifflist %s: %s",
                resp.status_code,
                (resp.text or "")[:900],
            )
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "tariff_codes" in data:
        return data["tariff_codes"]
    return []


def _cdek_calculator_tariff_entity(data: Any) -> dict[str, Any]:
    """Ответ POST /calculator/tariff: сущность в корне или в entity."""
    if not isinstance(data, dict):
        return {}
    ent = data.get("entity")
    if isinstance(ent, dict):
        return ent
    return data


async def get_calculator_tariff(
    from_city_code: int,
    to_city_code: int,
    tariff_code: int,
    weight_gram: int = 1000,
    length_cm: int = 10,
    width_cm: int = 10,
    height_cm: int = 10,
    *,
    shipment_point: Optional[str] = None,
    delivery_point: Optional[str] = None,
    services: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Расчёт по одному тарифу: POST /v2/calculator/tariff (тип Tariff в официальном PHP SDK СДЭК).

    Здесь же задаются дополнительные услуги (например страхование): ``services`` —
    ``[{"code": "INSURANCE", "parameter": <объявленная стоимость груза в ₽>}]``.
    В ответе: ``delivery_sum`` (базовая доставка), ``total_sum`` (с учётом услуг), массив ``services`` с суммами.

    Список тарифов без услуг — по-прежнему ``get_tariff_list`` (tarifflist); для точной суммы как в заказе
    после выбора ``tariff_code`` вызывайте этот метод с теми же городами/ПВЗ/габаритами и услугами,
    что уйдут в POST /orders (в т.ч. ``services`` на корне заказа).
    """
    base_url, _, _ = _get_config()
    token = await get_cdek_token()
    url = f"{base_url}/calculator/tariff"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    packages = [
        {
            "number": "1",
            "weight": int(weight_gram),
            "length": int(length_cm),
            "width": int(width_cm),
            "height": int(height_cm),
        }
    ]
    _lang = (os.getenv("CDEK_TARIFFLIST_LANG") or "rus").strip().lower()
    if _lang not in ("rus", "eng", "zho"):
        _lang = "rus"
    if shipment_point is None:
        sp = os.getenv("CDEK_SENDER_SHIPMENT_POINT", "USS3").strip() or None
    else:
        sp = shipment_point.strip() or None
    dp = (delivery_point or "").strip() or None

    body: dict[str, Any] = {
        "type": 1,
        "lang": _lang,
        "tariff_code": int(tariff_code),
        "packages": packages,
        "from_location": {"code": int(from_city_code)},
        "to_location": {"code": int(to_city_code)},
    }
    if dp:
        body["delivery_point"] = dp
    if sp:
        body["shipment_point"] = sp
    if services:
        body["services"] = services

    log_cdek_debug_request_body("POST /calculator/tariff", body)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=body, headers=headers)
        if resp.status_code == 400 and sp:
            logger.warning(
                "CDEK POST /calculator/tariff 400 (shipment_point=%s), повтор без shipment_point: %s",
                sp,
                (resp.text or "")[:900],
            )
            body_fb = {k: v for k, v in body.items() if k != "shipment_point"}
            body_fb.setdefault("from_location", {"code": int(from_city_code)})
            body_fb.setdefault("to_location", {"code": int(to_city_code)})
            log_cdek_debug_request_body("POST /calculator/tariff (fallback from_location)", body_fb)
            resp = await client.post(url, json=body_fb, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "CDEK POST /calculator/tariff %s: %s",
                resp.status_code,
                (resp.text or "")[:900],
            )
        resp.raise_for_status()
        data = resp.json()
    return _cdek_calculator_tariff_entity(data)


class CdekClient:
    """Тонкая обёртка для удобного доступа к методам СДЭК."""

    @staticmethod
    async def get_token() -> str:
        return await get_cdek_token()

    @staticmethod
    async def delivery_points(city_code: int) -> list[dict[str, Any]]:
        return await get_delivery_points(city_code)

    @staticmethod
    async def cities(
        country_code: str = "RU",
        city_name: Optional[str] = None,
        size: int = 30,
    ) -> list[dict[str, Any]]:
        return await get_cities(country_code=country_code, city_name=city_name, size=size)


def get_cdek_client() -> CdekClient:
    return CdekClient()
