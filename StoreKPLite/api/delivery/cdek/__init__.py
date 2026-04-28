"""
Клиент и утилиты для интеграции с API СДЭК v2.
"""

from api.delivery.cdek.client import (
    CDEK_SERVICE_CODE_INSURANCE,
    CdekClient,
    cdek_insurance_services,
    get_cdek_client,
    get_cdek_token,
    get_calculator_tariff,
    get_delivery_points,
    get_cities,
    get_tariff_list,
    log_cdek_debug_request_body,
    resolve_city_code,
)

__all__ = [
    "CDEK_SERVICE_CODE_INSURANCE",
    "CdekClient",
    "cdek_insurance_services",
    "get_cdek_client",
    "get_cdek_token",
    "get_calculator_tariff",
    "get_delivery_points",
    "get_cities",
    "get_tariff_list",
    "log_cdek_debug_request_body",
    "resolve_city_code",
]
