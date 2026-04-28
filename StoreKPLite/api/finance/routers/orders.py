"""
Роутер для обработки событий заказов от products-service
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
from os import getenv
import logging

from api.finance.database.database import get_session
from api.finance.models.account_balance import AccountBalance
from api.finance.models.account_transaction import AccountTransaction
from api.finance.models.finance_settings import FinanceSettings

logger = logging.getLogger(__name__)

router = APIRouter()

INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")


class OrderStatusUpdateRequest(BaseModel):
    """Запрос на обновление статуса заказа"""
    order_id: int
    old_status: str
    new_status: str
    paid_amount: Decimal
    refund_on_cancel: Optional[bool] = None
    admin_user_id: Optional[int] = None  # Внутренний ID админа из users-service


async def verify_internal_token(x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")):
    """Проверка внутреннего токена для межсервисного взаимодействия"""
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный внутренний токен")
    return True


@router.post("/internal/orders/status-update")
async def handle_order_status_update(
    request: OrderStatusUpdateRequest,
    _token_check = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session)
):
    """Обработка изменения статуса заказа из products-service"""
    
    # Обрабатываем только завершение заказа или отмену без возврата
    should_update_balances = False
    if request.new_status == "завершен" and request.old_status != "завершен":
        should_update_balances = True
    elif request.new_status == "отменен" and request.old_status != "отменен":
        # Отмена без возврата = прибыль (предоплата остается)
        if request.refund_on_cancel is False:
            should_update_balances = True
    
    if not should_update_balances:
        return {"message": "Статус не требует обновления балансов"}
    
    paid_amount = request.paid_amount or Decimal(0)
    if paid_amount <= 0:
        return {"message": "Сумма оплаты равна нулю, балансы не обновляются"}
    
    try:
        # Получаем настройки финансов
        settings_result = await session.execute(select(FinanceSettings).limit(1))
        settings = settings_result.scalar_one_or_none()
        if not settings:
            # Создаем настройки по умолчанию
            settings = FinanceSettings(
                depreciation_percent=Decimal("3.00"),
                working_capital_limit=None,
                delivery_cost_per_kg=None,
                exchange_rate_margin_percent=Decimal("10.00")
            )
            session.add(settings)
            await session.flush()
        
        depreciation_percent = settings.depreciation_percent or Decimal("3.00")
        
        # Получаем или создаем счета
        depreciation_balance_result = await session.execute(
            select(AccountBalance).where(AccountBalance.account_type == "depreciation_fund")
        )
        depreciation_balance = depreciation_balance_result.scalar_one_or_none()
        if not depreciation_balance:
            depreciation_balance = AccountBalance(account_type="depreciation_fund", balance=Decimal(0))
            session.add(depreciation_balance)
        
        working_balance_result = await session.execute(
            select(AccountBalance).where(AccountBalance.account_type == "working_capital")
        )
        working_balance = working_balance_result.scalar_one_or_none()
        if not working_balance:
            working_balance = AccountBalance(account_type="working_capital", balance=Decimal(0))
            session.add(working_balance)
        
        free_balance_result = await session.execute(
            select(AccountBalance).where(AccountBalance.account_type == "free_capital")
        )
        free_balance = free_balance_result.scalar_one_or_none()
        if not free_balance:
            free_balance = AccountBalance(account_type="free_capital", balance=Decimal(0))
            session.add(free_balance)
        
        await session.flush()  # Обновляем балансы в БД чтобы получить актуальные значения
        
        # Процент из настроек идет в амортизационный фонд
        depreciation_amount = paid_amount * (depreciation_percent / Decimal("100"))
        depreciation_balance.balance += depreciation_amount
        
        # Остаток идет в оборотный счет
        working_amount = paid_amount - depreciation_amount
        working_balance.balance += working_amount
        
        # Проверяем лимит оборотного капитала и переводим излишек в свободный капитал
        if settings.working_capital_limit and working_balance.balance > settings.working_capital_limit:
            excess = working_balance.balance - settings.working_capital_limit
            working_balance.balance = settings.working_capital_limit
            free_balance.balance += excess
            
            # Создаем запись о переводе излишка
            transfer_transaction = AccountTransaction(
                transaction_type="transfer",
                account_from="working_capital",
                account_to="free_capital",
                amount=excess,
                created_by_user_id=request.admin_user_id,
                notes=f"Автоматический перевод излишка оборотного капитала (превышен лимит {settings.working_capital_limit} ₽)",
            )
            session.add(transfer_transaction)
        
        # Определяем тип операции для текста
        if request.new_status == "завершен":
            operation_type = "завершении"
        else:
            operation_type = "отмене без возврата"
        
        # Создаем записи об операциях
        depreciation_transaction = AccountTransaction(
            transaction_type="deposit",
            account_to="depreciation_fund",
            amount=depreciation_amount,
            created_by_user_id=request.admin_user_id,
            notes=f"Автоматическое пополнение при {operation_type} заказа #{request.order_id} ({depreciation_percent}% от {paid_amount} ₽)",
        )
        session.add(depreciation_transaction)
        
        working_transaction = AccountTransaction(
            transaction_type="deposit",
            account_to="working_capital",
            amount=working_amount,
            created_by_user_id=request.admin_user_id,
            notes=f"Автоматическое пополнение при {operation_type} заказа #{request.order_id} ({100 - depreciation_percent}% от {paid_amount} ₽)",
        )
        session.add(working_transaction)
        
        await session.commit()
        
        logger.info(
            f"Балансы обновлены для заказа #{request.order_id}: "
            f"depreciation={depreciation_amount} ₽, working={working_amount} ₽"
        )
        
        return {
            "message": "Балансы успешно обновлены",
            "depreciation_amount": float(depreciation_amount),
            "working_amount": float(working_amount),
        }
    
    except Exception as e:
        logger.error(f"Ошибка при обновлении балансов для заказа #{request.order_id}: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении балансов: {str(e)}")

