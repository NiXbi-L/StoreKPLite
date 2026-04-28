"""
Общий запрос к finance-service: курс, доставка и параметры ценообразования одним вызовом.
"""
from decimal import Decimal
from typing import NamedTuple, Optional
import os
import logging
import httpx

logger = logging.getLogger(__name__)

FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://finance-service:8003")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")
_DEFAULT_RATE = Decimal("12.5")
_DEFAULT_ACQUIRING = Decimal("0.97")


class FinancePriceContext(NamedTuple):
    """Курс ``rate_with_margin`` — юань→руб с наценкой (издержки конвертации); один для клиента и владельца."""

    rate_with_margin: Decimal
    delivery_cost_per_kg: Optional[Decimal]
    yuan_markup_before_rub_percent: Decimal
    customer_price_acquiring_factor: Decimal


def finance_price_context_for_owner_checkout(ctx: FinancePriceContext) -> FinancePriceContext:
    """
    Заказ / просмотр владельца (admin_type=owner): маркер контекста для удельной «закупки» (юани×курс с маржой
    finance + доставка по весу, без торгового % на юани, без сервисного сбора и без эквайринга) — см.
    compute_item_unit_price_for_ctx в item_pricing. Курс и доставка за кг — как в обычном контексте.
    """
    return FinancePriceContext(
        ctx.rate_with_margin,
        ctx.delivery_cost_per_kg,
        Decimal("0"),
        Decimal("1"),
    )


async def get_finance_price_context() -> FinancePriceContext:
    """
    Один запрос к finance: GET /internal/price-context.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{FINANCE_SERVICE_URL}/internal/price-context",
                headers={"X-Internal-Token": INTERNAL_TOKEN},
            )
            if response.status_code == 200:
                data = response.json()
                rate = Decimal(str(data.get("rate_with_margin", _DEFAULT_RATE)))
                d = data.get("delivery_cost_per_kg")
                delivery = Decimal(str(d)) if d is not None else None
                yp = data.get("yuan_markup_before_rub_percent")
                yuan_pct = Decimal(str(yp)) if yp is not None else Decimal("0")
                af = data.get("customer_price_acquiring_factor")
                acq = Decimal(str(af)) if af is not None else _DEFAULT_ACQUIRING
                return FinancePriceContext(rate, delivery, yuan_pct, acq)
    except Exception as e:
        logger.warning("Ошибка при получении price-context из finance: %s", e)
    return FinancePriceContext(_DEFAULT_RATE, None, Decimal("0"), _DEFAULT_ACQUIRING)
