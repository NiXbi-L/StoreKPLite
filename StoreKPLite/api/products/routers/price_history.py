"""
Роутер для управления историей цен товаров
"""
from datetime import timedelta
from decimal import Decimal
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.database.database import get_session
from api.products.models.item import Item
from api.products.models.item_price_history import ItemPriceHistory
from api.shared.timezone import get_current_4h_bucket_start_vladivostok, now_vladivostok
from api.products.utils.finance_context import get_finance_price_context, FinancePriceContext
from api.products.utils.item_pricing import compute_item_customer_price_rub
from os import getenv

logger = logging.getLogger(__name__)

router = APIRouter()

INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")


async def calculate_item_price(item: Item, ctx: FinancePriceContext) -> Decimal:
    return compute_item_customer_price_rub(
        item,
        ctx.rate_with_margin,
        ctx.delivery_cost_per_kg,
        yuan_markup_before_rub_percent=ctx.yuan_markup_before_rub_percent,
        customer_price_acquiring_factor=ctx.customer_price_acquiring_factor,
    )


def check_internal_token(token: Optional[str] = None) -> bool:
    """Проверка внутреннего токена для межсервисного взаимодействия"""
    if not token:
        return False
    # Убираем возможный префикс "Bearer " если есть
    clean_token = token.replace("Bearer ", "").strip() if token.startswith("Bearer") else token.strip()
    return clean_token == INTERNAL_TOKEN


async def upsert_price_history_4h_bucket(
    session: AsyncSession,
    item_id: int,
    price_rub: Decimal,
) -> bool:
    """
    Обновляет или создаёт запись истории за текущее 4h-окно (Владивосток).
    Возвращает True если создана новая запись, False если обновлена.
    """
    from sqlalchemy import and_
    bucket_start_dt = get_current_4h_bucket_start_vladivostok()
    result = await session.execute(
        select(ItemPriceHistory).where(
            and_(
                ItemPriceHistory.item_id == item_id,
                ItemPriceHistory.week_start == bucket_start_dt,
            )
        )
    )
    row = result.scalar_one_or_none()
    if row:
        # Бегущее среднее: new_avg = (avg * count + price) / (count + 1)
        count = row.sample_count or 1
        old_avg = row.avg_price if row.avg_price is not None else (row.min_price + row.max_price) / 2
        row.avg_price = (old_avg * count + price_rub) / (count + 1)
        row.sample_count = count + 1
        if price_rub < row.min_price:
            row.min_price = price_rub
        if price_rub > row.max_price:
            row.max_price = price_rub
        return False
    else:
        session.add(
            ItemPriceHistory(
                item_id=item_id,
                week_start=bucket_start_dt,
                min_price=price_rub,
                max_price=price_rub,
                avg_price=price_rub,
                sample_count=1,
            )
        )
        return True


async def delete_price_history_older_than_days(
    session: AsyncSession,
    days: int = 7,
) -> int:
    """
    Удаляет записи истории цен старше указанного числа дней.
    Вызывается при каждом пересчёте истории, чтобы не засорять БД.
    """
    cutoff = now_vladivostok() - timedelta(days=days)
    result = await session.execute(delete(ItemPriceHistory).where(ItemPriceHistory.week_start < cutoff))
    deleted = result.rowcount if hasattr(result, "rowcount") else 0
    if deleted and deleted > 0:
        logger.info(f"Удалено записей истории цен старше {days} дн.: {deleted}")
    return deleted


@router.post("/internal/recalculate-price-history")
async def recalculate_price_history(
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")
):
    """
    Пересчитать историю цен для всех товаров (внутренний эндпоинт).
    Вызывается finance-service после обновления курса валюты.
    """
    # Проверка внутреннего токена через заголовок
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    try:
        ctx = await get_finance_price_context()

        # Получаем все товары
        items_result = await session.execute(select(Item))
        items = items_result.scalars().all()
        
        updated_count = 0
        created_count = 0
        
        for item in items:
            new_price_rub = await calculate_item_price(item, ctx)
            is_new = await upsert_price_history_4h_bucket(session, item.id, new_price_rub)
            if is_new:
                created_count += 1
            else:
                updated_count += 1
        
        # Удаляем записи старше 7 дней, чтобы не засорять БД
        deleted_count = await delete_price_history_older_than_days(session, days=7)
        
        await session.commit()
        
        logger.info(
            f"История цен пересчитана: обновлено {updated_count}, создано {created_count}, удалено старых {deleted_count}"
        )
        
        return {
            "success": True,
            "updated": updated_count,
            "created": created_count,
            "deleted_old": deleted_count,
            "total_items": len(items),
        }
    
    except Exception as e:
        logger.error(f"Ошибка при пересчете истории цен: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при пересчете истории цен: {str(e)}")

