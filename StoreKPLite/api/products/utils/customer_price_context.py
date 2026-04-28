"""
Контекст цены для отображения в миниаппе: владельцу подставляется owner-checkout контекст — по нему
считается удельная закупка (см. compute_item_unit_price_for_ctx), а не витринная цена покупателя.
"""
from __future__ import annotations

from typing import Optional

from api.products.utils.finance_context import (
    FinancePriceContext,
    finance_price_context_for_owner_checkout,
)
from api.shared.auth import get_bearer_jwt_admin_type_optional


async def finance_ctx_with_owner_display(
    base_ctx: FinancePriceContext,
    authorization: Optional[str],
) -> FinancePriceContext:
    """Если в Authorization — JWT владельца (admin_type=owner), подменить параметры ценообразования."""
    at = await get_bearer_jwt_admin_type_optional(authorization)
    if at == "owner":
        return finance_price_context_for_owner_checkout(base_ctx)
    return base_ctx
