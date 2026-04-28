"""
Роутер для работы с платежами через ЮKassa
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from os import getenv
import httpx
import uuid
import logging
from datetime import datetime

from api.finance.database.database import get_session
from api.finance.models.payment import Payment
from api.finance.models.refund_log import RefundLog
from api.finance.utils.first_ofd_consumer_url import first_ofd_ticket_url_from_yookassa_receipt
from api.finance.utils.yookassa_receipt_client import (
    get_yookassa_receipt,
    list_receipts_for_yookassa_payment,
    pick_payment_receipt_id,
)
from api.shared.auth import HTTPBearer, verify_jwt_token
from api.shared.admin_permissions import has_admin_permission
from api.shared.jwt_admin_deps import require_jwt_permission
from api.shared.tg_notify_copy import MINIAPP_ORDERS_HINT, SUPPORT_VIA_CHANNEL_HINT

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()
_bearer_optional = HTTPBearer(auto_error=False)

# Конфигурация ЮKassa
YOOKASSA_SHOP_ID = getenv("YOOKASSA_SHOP_ID")
YOOKASSA_API_TOKEN = getenv("YOOKASSA_API_TOKEN")
YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"
YOOKASSA_REFUNDS_URL = "https://api.yookassa.ru/v3/refunds"

_DEFAULT_INTERNAL_TOKEN = "internal-secret-token-change-in-production"
INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", _DEFAULT_INTERNAL_TOKEN)
PRODUCTS_SERVICE_URL = getenv("PRODUCTS_SERVICE_URL", "http://products-service:8002")
USERS_SERVICE_URL = getenv("USERS_SERVICE_URL", "http://users-service:8001")

if INTERNAL_TOKEN == _DEFAULT_INTERNAL_TOKEN:
    logger.warning(
        "INTERNAL_TOKEN не задан — используется значение по умолчанию. "
        "В проде задайте INTERNAL_TOKEN в окружении для защиты внутренних эндпоинтов."
    )

# Код ставки НДС в чеке ЮKassa (параметр vat_code). Справочник:
# https://yookassa.ru/developers/payment-acceptance/receipts/54fz/yoomoney/parameters-values
# 1 = без НДС (типично для УСН); 4 = НДС 20%; 11/12 — повышенные ставки с 2026 г. и т.д.
YOOKASSA_VAT_CODE_NO_VAT = 1

# Отмена заказа при отмене платежа ЮKassa (причина в БД + единый тон уведомления)
PAYMENT_CANCELED_ORDER_REASON = (
    "Платёж по заказу был отменён, поэтому заказ отменён. "
    "Свяжитесь со службой поддержки, если остались вопросы, или оформите заказ повторно."
)


# Pydantic схемы
class ReceiptItem(BaseModel):
    """Позиция в чеке"""
    description: str
    quantity: str  # Количество (строка для точности)
    amount: Dict[str, str]  # {"value": "100.00", "currency": "RUB"}
    vat_code: Optional[int] = YOOKASSA_VAT_CODE_NO_VAT  # по умолчанию «без НДС» (ЮKassa)
    payment_mode: Optional[str] = None  # Режим оплаты (например, "full_prepayment" для предоплаты)
    payment_subject: Optional[str] = None  # Предмет расчета


class CreatePaymentRequest(BaseModel):
    """Запрос на создание платежа"""
    order_id: int
    user_id: Optional[int] = None
    amount: Decimal
    description: Optional[str] = None
    return_url: str
    metadata: Optional[Dict[str, Any]] = None
    receipt_items: Optional[List[ReceiptItem]] = None  # Позиции чека
    customer_email: Optional[str] = None  # Email клиента для чека
    customer_phone: Optional[str] = None  # Телефон клиента для чека


class PaymentResponse(BaseModel):
    """Ответ с данными платежа"""
    id: int
    order_id: int
    user_id: Optional[int]
    yookassa_payment_id: Optional[str]
    amount: Decimal
    currency: str
    description: Optional[str]
    status: str
    paid: bool
    confirmation_url: Optional[str]
    return_url: Optional[str]
    payment_metadata: Optional[Dict[str, Any]] = None
    test: bool
    created_at: datetime
    updated_at: datetime
    paid_at: Optional[datetime]
    receipt_registration: Optional[str] = None
    yookassa_receipt_id: Optional[str] = None
    has_receipt_pdf: bool = False
    ofd_receipt_url: Optional[str] = None

    class Config:
        from_attributes = True


class PaymentStatusResponse(BaseModel):
    """Ответ со статусом платежа"""
    payment_id: str
    status: str
    paid: bool
    amount: Dict[str, Any]
    created_at: str
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


async def verify_internal_token(x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")):
    """Проверка внутреннего токена для межсервисного взаимодействия"""
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный внутренний токен")
    return True


check_admin_access = require_jwt_permission("orders")


def _json_safe_receipt_items(items: Optional[List[Dict[str, Any]]]) -> Optional[Any]:
    """Сериализация позиций чека для JSON-поля в БД."""
    import json

    if not items:
        return None
    try:
        return json.loads(json.dumps(items, default=str))
    except Exception:
        return None


async def _hydrate_payment_ofd_consumer_url(session: AsyncSession, payment: Payment) -> None:
    """Сохранить ссылку consumer.1-ofd.ru по данным чека ЮKassa (без повторной записи)."""
    if payment.ofd_receipt_url or not payment.yookassa_payment_id:
        return
    rid = payment.yookassa_receipt_id
    if not rid:
        receipts = await list_receipts_for_yookassa_payment(payment.yookassa_payment_id)
        rid = pick_payment_receipt_id(receipts)
        if rid:
            payment.yookassa_receipt_id = rid
    if not rid:
        return
    detail = await get_yookassa_receipt(rid)
    if not detail:
        return
    url = first_ofd_ticket_url_from_yookassa_receipt(detail)
    if url:
        payment.ofd_receipt_url = url


async def _try_send_payment_ofd_receipt_telegram(session: AsyncSession, payment: Payment) -> None:
    if not payment.ofd_receipt_url or payment.ofd_receipt_telegram_sent or not payment.paid:
        return
    if not payment.order_id:
        return
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            order_response = await client.get(
                f"{PRODUCTS_SERVICE_URL}/internal/orders/{payment.order_id}",
                headers={"X-Internal-Token": INTERNAL_TOKEN},
            )
            if order_response.status_code != 200:
                return
            order_data = order_response.json()
            user_id = order_data.get("user_id")
            if not user_id:
                return
            user_response = await client.get(f"{USERS_SERVICE_URL}/users/{user_id}", timeout=8.0)
            if user_response.status_code != 200:
                return
            user_data = user_response.json()
            tgid = user_data.get("tgid")
            if not tgid:
                return
            text = (
                f"Документ по оплате заказа #{payment.order_id} (ссылка действительна как на сайте ОФД):\n"
                f"{payment.ofd_receipt_url}\n\n{MINIAPP_ORDERS_HINT}"
            )
            await _send_telegram_message(int(tgid), text)
            payment.ofd_receipt_telegram_sent = True
            await session.commit()
    except Exception as e:
        logger.warning("Не удалось отправить ссылку ОФД в Telegram для платежа %s: %s", payment.id, e)


async def create_yookassa_payment(
    amount: Decimal,
    description: Optional[str],
    return_url: str,
    metadata: Optional[Dict[str, Any]] = None,
    receipt_items: Optional[List[Dict[str, Any]]] = None,
    customer_email: Optional[str] = None,
    customer_phone: Optional[str] = None,
    capture: bool = False
) -> Dict[str, Any]:
    """
    Создать платеж в ЮKassa
    
    Args:
        amount: Сумма платежа в рублях
        description: Описание платежа
        return_url: URL возврата после оплаты
        metadata: Дополнительные метаданные
    
    Returns:
        Словарь с данными созданного платежа
    """
    # Валидация суммы
    if amount <= 0:
        raise ValueError("Сумма платежа должна быть больше 0")
    if amount < Decimal("0.01"):
        raise ValueError("Минимальная сумма платежа: 0.01 ₽")
    
    if not YOOKASSA_SHOP_ID or not YOOKASSA_API_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ЮKassa не настроена. Проверьте YOOKASSA_SHOP_ID и YOOKASSA_API_TOKEN"
        )
    
    # Генерируем ключ идемпотентности
    idempotence_key = str(uuid.uuid4())
    
    # Формируем запрос к ЮKassa
    payment_data = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "capture": capture,  # Холдирование или немедленное списание
        "confirmation": {
            "type": "redirect",
            "return_url": return_url
        }
    }
    
    if description:
        payment_data["description"] = description[:128]  # Максимум 128 символов
    
    if metadata:
        payment_data["metadata"] = metadata
    
    # Добавляем чек, если есть позиции
    if receipt_items:
        customer_data: Dict[str, Any] = {}
        email_clean = (customer_email or "").strip()
        if email_clean:
            customer_data["email"] = email_clean
        phone_clean = ""
        if customer_phone:
            phone_clean = (
                str(customer_phone)
                .replace(" ", "")
                .replace("-", "")
                .replace("(", "")
                .replace(")", "")
            )
        if phone_clean:
            customer_data["phone"] = phone_clean
        if not customer_data:
            raise HTTPException(
                status_code=400,
                detail="Для чека 54-ФЗ передайте customer_phone или customer_email покупателя.",
            )
        payment_data["receipt"] = {
            "customer": customer_data,
            "items": receipt_items
        }
    
    # Отправляем запрос к ЮKassa
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                YOOKASSA_API_URL,
                json=payment_data,
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_API_TOKEN),
                headers={
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            return {
                "yookassa_data": response.json(),
                "idempotence_key": idempotence_key
            }
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка при создании платежа в ЮKassa: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Ошибка при создании платежа в ЮKassa: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Ошибка сети при создании платежа в ЮKassa: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка сети при создании платежа: {str(e)}"
        )


@router.post("/payments", response_model=PaymentResponse)
async def create_payment(
    request: CreatePaymentRequest,
    admin = Depends(check_admin_access),
    session: AsyncSession = Depends(get_session)
):
    """
    Создать платеж через ЮKassa
    
    Создает платеж в ЮKassa и сохраняет его в БД.
    Возвращает данные платежа с URL для редиректа пользователя на оплату.
    """
    try:
        # Проверяем, нет ли уже активного платежа для этого заказа
        existing_payment = (await session.execute(
            select(Payment).where(
                Payment.order_id == request.order_id,
                Payment.status.in_(["pending", "waiting_for_capture", "succeeded"])
            )
        )).scalar_one_or_none()
        
        if existing_payment:
            raise HTTPException(
                status_code=400,
                detail=f"Для заказа {request.order_id} уже существует активный платеж (ID: {existing_payment.id})"
            )
        
        # Преобразуем receipt_items в формат для ЮKassa
        receipt_items_dict = None
        if request.receipt_items:
            receipt_items_dict = [item.model_dump() for item in request.receipt_items]
        
        # Создаем платеж в ЮKassa
        yookassa_result = await create_yookassa_payment(
            amount=request.amount,
            description=request.description,
            return_url=request.return_url,
            metadata=request.metadata,
            receipt_items=receipt_items_dict,
            customer_email=request.customer_email,
            customer_phone=request.customer_phone
        )
        
        yookassa_data = yookassa_result["yookassa_data"]
        idempotence_key = yookassa_result["idempotence_key"]
        
        # Сохраняем платеж в БД
        payment = Payment(
            order_id=request.order_id,
            user_id=request.user_id,
            yookassa_payment_id=yookassa_data.get("id"),
            amount=request.amount,
            currency="RUB",
            description=request.description,
            status=yookassa_data.get("status", "pending"),
            paid=yookassa_data.get("paid", False),
            confirmation_url=yookassa_data.get("confirmation", {}).get("confirmation_url"),
            return_url=request.return_url,
            payment_metadata=request.metadata or yookassa_data.get("metadata"),
            test=yookassa_data.get("test", False),
            idempotence_key=idempotence_key,
            receipt_items_json=_json_safe_receipt_items(receipt_items_dict),
        )
        
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        
        logger.info(f"Создан платеж ID={payment.id} для заказа {request.order_id}, ЮKassa ID={yookassa_data.get('id')}")
        
        return payment
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при создании платежа: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при создании платежа: {str(e)}")


@router.post("/payments/create", response_model=PaymentResponse)
async def create_payment_public(
    http_request: Request,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session)
):
    """
    Создать платеж через ЮKassa (публичный endpoint для ботов)
    
    Использует внутренний токен для авторизации. Проверяет, что заказ принадлежит пользователю.
    """
    # Проверка внутреннего токена
    if not x_internal_token or x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Требуется внутренний токен")
    
    # Парсим JSON из тела запроса
    try:
        request_data = await http_request.json()
    except Exception as e:
        logger.error(f"Ошибка парсинга JSON: {e}")
        raise HTTPException(status_code=400, detail=f"Ошибка парсинга JSON: {str(e)}")
    
    # Преобразуем receipt_items из словарей в модели ReceiptItem, если они есть
    receipt_items_models = None
    if request_data.get("receipt_items"):
        receipt_items_models = []
        for item in request_data["receipt_items"]:
            if isinstance(item, dict):
                try:
                    receipt_items_models.append(ReceiptItem(**item))
                except Exception as e:
                    logger.error(f"Ошибка валидации receipt_item: {e}, item: {item}")
                    raise HTTPException(status_code=400, detail=f"Ошибка валидации receipt_item: {str(e)}")
            else:
                receipt_items_models.append(item)
    
    # Валидация суммы платежа
    amount_value = Decimal(str(request_data["amount"]))
    if amount_value <= 0:
        raise HTTPException(status_code=400, detail="Сумма платежа должна быть больше 0")
    if amount_value < Decimal("0.01"):
        raise HTTPException(status_code=400, detail="Минимальная сумма платежа: 0.01 ₽")
    
    # Создаем валидированный запрос
    try:
        request = CreatePaymentRequest(
            order_id=request_data["order_id"],
            user_id=request_data.get("user_id"),
            amount=amount_value,
            description=request_data.get("description"),
            return_url=request_data["return_url"],
            metadata=request_data.get("metadata"),
            receipt_items=receipt_items_models,
            customer_email=request_data.get("customer_email"),
            customer_phone=request_data.get("customer_phone")
        )
    except Exception as e:
        logger.error(f"Ошибка валидации запроса на создание платежа: {e}, request_data: {request_data}")
        raise HTTPException(status_code=400, detail=f"Ошибка валидации запроса: {str(e)}")
    
    # Проверяем, что заказ существует и принадлежит пользователю через products-service
    if request.user_id:
        try:
            async with httpx.AsyncClient() as client:
                order_response = await client.get(
                    f"{PRODUCTS_SERVICE_URL}/internal/orders/{request.order_id}",
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    timeout=10.0
                )
                
                if order_response.status_code == 404:
                    raise HTTPException(status_code=404, detail="Заказ не найден")
                
                if order_response.status_code != 200:
                    raise HTTPException(
                        status_code=order_response.status_code,
                        detail="Ошибка при проверке заказа"
                    )
                
                order_data = order_response.json()
                # Проверяем, что заказ принадлежит пользователю (если user_id указан)
                # Для этого нужно получить user_id из заказа через products-service
                # Пока просто проверяем, что заказ существует
        except httpx.RequestError as e:
            logger.error(f"Ошибка при проверке заказа: {e}")
            raise HTTPException(status_code=500, detail="Ошибка при проверке заказа")
    
    # Используем ту же логику, что и в create_payment
    try:
        logger.info(f"Создание платежа для заказа {request.order_id}, сумма: {request.amount}, user_id: {request.user_id}")
        
        # Один платёж на заказ (100% оплата). Не разрешаем второй платёж.
        existing_payment = (await session.execute(
            select(Payment).where(
                Payment.order_id == request.order_id,
                Payment.status.in_(["pending", "waiting_for_capture"])
            )
        )).scalar_one_or_none()
        if existing_payment:
            logger.info(f"Для заказа {request.order_id} уже есть активный платёж {existing_payment.id}, возвращаем ссылку")
            return existing_payment
        
        # Всегда холдим — capture делается при переходе заказа в «в работе» / «Собран»
        should_capture = False
        
        # Преобразуем receipt_items в формат для ЮKassa
        receipt_items_dict = None
        if request.receipt_items:
            try:
                receipt_items_dict = [item.model_dump() for item in request.receipt_items]
                logger.info(f"Receipt items преобразованы: {len(receipt_items_dict)} позиций")
                # Логируем первую позицию для отладки
                if receipt_items_dict:
                    logger.info(f"Первая позиция чека: {receipt_items_dict[0]}")
            except Exception as e:
                logger.error(f"Ошибка при преобразовании receipt_items: {e}, items: {request.receipt_items}")
                raise HTTPException(status_code=400, detail=f"Ошибка при обработке позиций чека: {str(e)}")
        
        logger.info(f"Создание платежа в ЮKassa: amount={request.amount}, should_capture={should_capture}, receipt_items={len(receipt_items_dict) if receipt_items_dict else 0}, customer_phone={request.customer_phone}")
        
        # Создаем платеж в ЮKassa
        yookassa_result = await create_yookassa_payment(
            amount=request.amount,
            description=request.description,
            return_url=request.return_url,
            metadata=request.metadata,
            receipt_items=receipt_items_dict,
            customer_email=request.customer_email,
            customer_phone=request.customer_phone,
            capture=should_capture
        )
        
        yookassa_data = yookassa_result["yookassa_data"]
        idempotence_key = yookassa_result["idempotence_key"]
        
        # Сохраняем платеж в БД
        payment = Payment(
            order_id=request.order_id,
            user_id=request.user_id,
            yookassa_payment_id=yookassa_data.get("id"),
            amount=request.amount,
            currency="RUB",
            description=request.description,
            status=yookassa_data.get("status", "pending"),
            paid=yookassa_data.get("paid", False),
            confirmation_url=yookassa_data.get("confirmation", {}).get("confirmation_url"),
            return_url=request.return_url,
            payment_metadata=request.metadata or yookassa_data.get("metadata"),
            test=yookassa_data.get("test", False),
            idempotence_key=idempotence_key,
            receipt_items_json=_json_safe_receipt_items(receipt_items_dict),
        )
        
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        
        logger.info(f"Создан платеж ID={payment.id} для заказа {request.order_id}, ЮKassa ID={yookassa_data.get('id')}")
        
        return payment
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при создании платежа: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при создании платежа: {str(e)}")


@router.get("/internal/payments/{payment_id}/receipt-pdf")
async def internal_download_payment_receipt_pdf(
    payment_id: int,
    order_id: int = Query(..., description="ID заказа — должен совпадать с платежом"),
    _ok: bool = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session),
):
    """
    PDF-справка по позициям, переданным в ЮKassa при создании платежа.
    Не фискальный чек; для старых платежей без receipt_items_json вернёт 404.
    """
    payment = (await session.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not payment or payment.order_id != order_id:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    items = payment.receipt_items_json
    if not isinstance(items, list) or len(items) == 0:
        raise HTTPException(
            status_code=404,
            detail="Нет сохранённого состава чека (старый платёж или оплата без позиций в чеке)",
        )
    from api.finance.utils.receipt_pdf import build_payment_receipt_pdf_bytes

    pdf_bytes = build_payment_receipt_pdf_bytes(
        order_id=payment.order_id,
        payment_id=payment.id,
        amount=str(payment.amount),
        yookassa_payment_id=payment.yookassa_payment_id,
        yookassa_receipt_id=payment.yookassa_receipt_id,
        receipt_registration=payment.receipt_registration,
        items=items,
    )
    fn = f"receipt_order_{payment.order_id}_payment_{payment.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: int,
    admin = Depends(check_admin_access),
    session: AsyncSession = Depends(get_session)
):
    """Получить информацию о платеже по ID. Статус подтверждается через API ЮKassa."""
    payment = (await session.execute(
        select(Payment).where(Payment.id == payment_id)
    )).scalar_one_or_none()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Платеж не найден")
    
    payment = await sync_payment_status_from_yookassa(session, payment)
    return payment


@router.get("/payments/order/{order_id}", response_model=List[PaymentResponse])
async def get_payment_by_order(
    order_id: int,
    request: Request,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session)
):
    """Получить все платежи по ID заказа"""
    # Проверяем внутренний токен или админский доступ
    if x_internal_token and x_internal_token == INTERNAL_TOKEN:
        # Внутренний вызов - разрешаем
        pass
    else:
        credentials = await _bearer_optional(request)
        if not credentials:
            raise HTTPException(status_code=403, detail="Доступ запрещен")
        try:
            user_data = await verify_jwt_token(credentials)
        except HTTPException:
            raise HTTPException(status_code=403, detail="Доступ запрещен")
        if has_admin_permission(user_data, "orders"):
            pass
        else:
            user_id = user_data.get("user_id")
            if user_id is None:
                raise HTTPException(status_code=403, detail="Доступ запрещен")
            async with httpx.AsyncClient() as client:
                order_response = await client.get(
                    f"{PRODUCTS_SERVICE_URL}/internal/orders/{order_id}",
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    timeout=10.0
                )
                if order_response.status_code == 200:
                    order_data = order_response.json()
                    order_user_id = order_data.get("user_id")
                    if order_user_id != user_id:
                        raise HTTPException(
                            status_code=403,
                            detail="Доступ запрещен: заказ не принадлежит пользователю",
                        )
                else:
                    raise HTTPException(status_code=404, detail="Заказ не найден")
    
    payments = (await session.execute(
        select(Payment).where(Payment.order_id == order_id)
        .order_by(Payment.created_at.desc())
    )).scalars().all()
    
    if not payments:
        return []
    
    # Подтверждаем статус каждого платежа через ЮKassa перед отдачей
    for p in payments:
        await sync_payment_status_from_yookassa(session, p)
    return list(payments)


@router.post("/payments/{payment_id}/check-status")
async def check_payment_status(
    payment_id: int,
    admin = Depends(check_admin_access),
    session: AsyncSession = Depends(get_session)
):
    """
    Проверить статус платежа в ЮKassa и обновить в БД.
    Использует общий механизм синхронизации статуса через API ЮKassa.
    """
    payment = (await session.execute(
        select(Payment).where(Payment.id == payment_id)
    )).scalar_one_or_none()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Платеж не найден")
    
    if not payment.yookassa_payment_id:
        raise HTTPException(status_code=400, detail="У платежа нет ID в ЮKassa")
    
    payment = await sync_payment_status_from_yookassa(session, payment)
    logger.info(f"Статус платежа ID={payment.id} обновлен: {payment.status}, paid={payment.paid}")
    return payment


@router.post("/payments/webhook")
async def handle_payment_webhook_public(
    webhook_data: Dict[str, Any],
    session: AsyncSession = Depends(get_session)
):
    """
    Обработка webhook от ЮKassa (публичный endpoint).

    Настройте в личном кабинете ЮKassa URL уведомлений:
      https://<ваш-домен>/api/finance/payments/webhook

    Пример: https://tgwebapp.example.com/api/finance/payments/webhook
    """
    return await _process_payment_webhook(webhook_data, session)


@router.post("/internal/payments/webhook")
async def handle_payment_webhook(
    webhook_data: Dict[str, Any],
    _token_check = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session)
):
    """
    Обработка webhook от ЮKassa (для внутреннего использования)
    
    Этот endpoint должен вызываться из обработчика webhook ЮKassa
    для обновления статуса платежа в БД.
    """
    return await _process_payment_webhook(webhook_data, session)


async def _fetch_payment_from_yookassa(yookassa_payment_id: str) -> Optional[Dict[str, Any]]:
    """Запросить актуальные данные платежа у ЮKassa API. Используется для проверки webhook."""
    if not YOOKASSA_SHOP_ID or not YOOKASSA_API_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{YOOKASSA_API_URL}/{yookassa_payment_id}",
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_API_TOKEN),
                headers={"Content-Type": "application/json"},
            )
            if response.status_code != 200:
                logger.warning(f"ЮKassa API вернул {response.status_code} для платежа {yookassa_payment_id}")
                return None
            return response.json()
    except Exception as e:
        logger.warning(f"Ошибка при запросе платежа у ЮKassa: {e}")
        return None


async def sync_payment_status_from_yookassa(session: AsyncSession, payment: Payment) -> Payment:
    """
    Подтвердить статус платежа через API ЮKassa и обновить запись в БД.
    Вызывать при любой работе с платежом, чтобы не опираться только на данные из БД.
    При ошибке API возвращает платеж без изменений (логируем предупреждение).
    """
    if not payment.yookassa_payment_id:
        return payment
    api_data = await _fetch_payment_from_yookassa(payment.yookassa_payment_id)
    if not api_data:
        logger.warning(f"Не удалось получить статус платежа {payment.id} из ЮKassa, используем данные из БД")
        return payment
    payment.status = api_data.get("status", payment.status)
    payment.paid = api_data.get("paid", payment.paid)
    rr = api_data.get("receipt_registration")
    if rr is not None:
        payment.receipt_registration = rr
    if payment.paid and not payment.paid_at:
        captured_at = api_data.get("captured_at")
        if captured_at:
            try:
                payment.paid_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
    if payment.yookassa_payment_id and not payment.yookassa_receipt_id:
        receipts = await list_receipts_for_yookassa_payment(payment.yookassa_payment_id)
        chosen = pick_payment_receipt_id(receipts)
        if chosen:
            payment.yookassa_receipt_id = chosen
    await _hydrate_payment_ofd_consumer_url(session, payment)
    await session.commit()
    await session.refresh(payment)
    logger.debug(f"Платеж {payment.id}: статус синхронизирован с ЮKassa — {payment.status}, paid={payment.paid}")
    await _try_send_payment_ofd_receipt_telegram(session, payment)
    return payment


async def _process_payment_webhook(
    webhook_data: Dict[str, Any],
    session: AsyncSession
) -> Dict[str, Any]:
    """
    Общая логика обработки webhook от ЮKassa.
    Для защиты от поддельных webhook данные о статусе/сумме берём из ЮKassa API (если доступен),
    а не из тела запроса.
    """
    event_type = webhook_data.get("event")
    payment_data = webhook_data.get("object", {})
    
    if event_type not in ["payment.succeeded", "payment.canceled", "payment.waiting_for_capture"]:
        logger.info(f"Игнорируем событие {event_type}")
        return {"status": "ignored"}
    
    yookassa_payment_id = payment_data.get("id")
    if not yookassa_payment_id:
        logger.error("В webhook отсутствует ID платежа")
        raise HTTPException(status_code=400, detail="Отсутствует ID платежа в webhook")
    
    # Находим платеж в БД (заказ) или платёж за AI-примерки
    payment = (await session.execute(
        select(Payment).where(Payment.yookassa_payment_id == yookassa_payment_id)
    )).scalar_one_or_none()

    if not payment:
        logger.info("Webhook: платёж %s не найден в orders (tryon-платежи отключены в StoreKPLite)", yookassa_payment_id)
        return {"status": "ignored", "reason": "tryon_payments_disabled"}
    
    # Проверка подлинности: запрашиваем актуальные данные у ЮKassa API
    api_payment = await _fetch_payment_from_yookassa(yookassa_payment_id)
    if api_payment:
        payment_data = api_payment  # Доверяем только ответу API
    # Если API недоступен — используем тело webhook (как раньше); в проде лучше иметь API настроенным
    
    # Сохраняем старый статус для проверки, был ли платеж в холде
    old_status = payment.status
    
    # Обновляем статус
    payment.status = payment_data.get("status", payment.status)
    payment.paid = payment_data.get("paid", payment.paid)
    
    if payment.paid and not payment.paid_at:
        captured_at = payment_data.get("captured_at")
        if captured_at:
            payment.paid_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    
    await session.commit()
    await session.refresh(payment)
    
    logger.info(f"Платеж ID={payment.id} обновлен через webhook: status={payment.status}, paid={payment.paid}, event_type={event_type}")
    
    # Уведомления клиенту по webhook не шлём: событие нужно только системе.
    # paid_amount по заказу продолжаем обновлять на основе суммы платежа.
    should_notify = False
    should_update_paid = True
    
    if event_type == "payment.waiting_for_capture":
        logger.info(f"Платеж {payment.id} в холде")
    elif event_type == "payment.succeeded":
        logger.info(f"Платеж {payment.id} успешно оплачен (captured_at={payment_data.get('captured_at')})")
    
    if should_update_paid and payment.order_id and event_type != "payment.canceled":
        try:
            amount_data = payment_data.get("amount", {})
            paid_amount = float(amount_data.get("value", 0))
            async with httpx.AsyncClient() as client:
                order_response = await client.get(
                    f"{PRODUCTS_SERVICE_URL}/internal/orders/{payment.order_id}",
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    timeout=10.0
                )
                if order_response.status_code == 200:
                    order_data = order_response.json()
                    user_id = order_data.get("user_id")
                    current_paid = float(order_data.get("paid_amount", 0))
                    # Один платёж: при холде ставим сумму платежа; при succeeded после capture не дублируем (уже стоит с холда).
                    # Если вебхук холда потерян, current_paid может быть 0 — берём max с суммой платежа.
                    if event_type == "payment.waiting_for_capture":
                        new_paid = paid_amount
                    elif event_type == "payment.succeeded" and payment_data.get("captured_at"):
                        new_paid = max(current_paid, paid_amount)
                    else:
                        new_paid = paid_amount
                    logger.info(f"paid_amount заказа {payment.order_id}: {current_paid:.2f} -> {new_paid:.2f} ₽")
                    update_response = await client.patch(
                        f"{PRODUCTS_SERVICE_URL}/internal/orders/{payment.order_id}/paid-amount",
                        json={"paid_amount": new_paid},
                        headers={"X-Internal-Token": INTERNAL_TOKEN},
                        timeout=10.0
                    )
                    if update_response.status_code == 200:
                        logger.info(f"Обновлен paid_amount для заказа {payment.order_id}: {new_paid:.2f} ₽")
                        is_from_stock = order_data.get("is_from_stock", False)
                        current_order_status = order_data.get("status")
                        if new_paid > 0:
                            # Заказы из наличия: после оплаты оставляем платёж в холде до сборки.
                            # Статус и capture обрабатываются в products (при переходе в «Собран») и finance (/internal/payments/capture-order-payments).
                            if is_from_stock:
                                logger.info(
                                    f"Заказ {payment.order_id} (наличие): оплата получена, платёж в холде; дальнейшая обработка при сборке заказа"
                                )
                            else:
                                # Заказы под заказ: после оплаты — статус "Выкуп", платёж остаётся в холде;
                                # capture выполняется при переходе заказа в "в работе" (capture_order_payments)
                                if current_order_status == "Ожидает":
                                    status_response = await client.post(
                                        f"{PRODUCTS_SERVICE_URL}/internal/orders/{payment.order_id}/status",
                                        json={"new_status": "Выкуп"},
                                        headers={"X-Internal-Token": INTERNAL_TOKEN},
                                        timeout=10.0
                                    )
                                    if status_response.status_code == 200:
                                        logger.info(f"Заказ {payment.order_id} (под заказ) переведен в статус 'Выкуп' после оплаты")
                        
                        # Уведомляем пользователя только если это первый платеж (холд или сразу принят)
                        if should_notify:
                            try:
                                logger.info(f"Начинаем отправку уведомления для заказа {payment.order_id}, user_id={user_id}")
                                # Получаем информацию о пользователе
                                user_tgid = None
                                user_vkid = None
                                order_platform = order_data.get("order_platform", "telegram")
                                
                                if user_id:
                                    logger.info(f"Получаем данные пользователя {user_id} из users-service")
                                    user_response = await client.get(
                                        f"{USERS_SERVICE_URL}/users/{user_id}",
                                        timeout=5.0
                                    )
                                    if user_response.status_code == 200:
                                        user_data = user_response.json()
                                        user_tgid = user_data.get("tgid")
                                        user_vkid = user_data.get("vkid")
                                        logger.info(f"Получены данные пользователя: tgid={user_tgid}, vkid={user_vkid}, platform={order_platform}")
                                    else:
                                        logger.warning(f"Не удалось получить данные пользователя {user_id}: {user_response.status_code}")
                                else:
                                    logger.warning(f"user_id не указан для заказа {payment.order_id}")
                                
                                # Один платёж — одно сообщение об оплате
                                order_items = order_data.get("order_data", {}).get("items", [])
                                order_total = sum(item.get("price", 0) * item.get("quantity", 1) for item in order_items)
                                text = f"✅ Оплата по заказу #{payment.order_id} успешно внесена!\n\n"
                                text += f"💰 Внесено: {paid_amount:.2f} ₽\n"
                                if order_total:
                                    text += f"💵 Сумма заказа: {order_total:.2f} ₽\n"
                                text += f"\n🎉 Заказ оплачен.\n{MINIAPP_ORDERS_HINT}"
                                
                                # Уведомления только в Telegram (миниап только в TG)
                                if user_tgid:
                                    logger.info(f"Отправляем уведомление в Telegram пользователю {user_tgid}")
                                    await _send_telegram_message(user_tgid, text)
                                    logger.info(f"Уведомление успешно отправлено для заказа {payment.order_id}")
                                else:
                                    logger.warning(f"Уведомление не отправлено для заказа {payment.order_id}: нет tgid")
                            except Exception as notify_error:
                                logger.error(f"Ошибка при отправке уведомления пользователю: {notify_error}", exc_info=True)
                                # Не прерываем выполнение webhook
                    else:
                        logger.warning(f"Не удалось обновить paid_amount для заказа {payment.order_id}: {update_response.status_code}")
                else:
                    logger.warning(f"Не удалось получить информацию о заказе {payment.order_id}: {order_response.status_code}")
        except Exception as e:
            logger.error(f"Ошибка при обновлении заказа после успешной оплаты: {e}", exc_info=True)
            # Не прерываем выполнение webhook
    
    # Если платеж отменен, обрабатываем отмену
    elif event_type == "payment.canceled":
        logger.info(f"Обрабатываем отмену платежа ID={payment.id} для заказа {payment.order_id}")
        try:
            # Проверяем, был ли платеж в холде перед отменой
            # Используем old_status, который был сохранен до обновления статуса
            # Если старый статус был "waiting_for_capture", значит платеж был в холде
            was_holded = old_status == "waiting_for_capture"
            
            # Проверяем, сколько платежей было для этого заказа до этого
            previous_payments = (await session.execute(
                select(Payment).where(
                    Payment.order_id == payment.order_id,
                    Payment.created_at < payment.created_at
                ).order_by(Payment.created_at.asc())
            )).scalars().all()
            
            is_first_payment = len(previous_payments) == 0
            
            # Получаем информацию о заказе и пользователе
            async with httpx.AsyncClient() as client:
                # Получаем информацию о заказе
                order_response = await client.get(
                    f"{PRODUCTS_SERVICE_URL}/internal/orders/{payment.order_id}",
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    timeout=10.0
                )
                
                if order_response.status_code == 200:
                    order_data = order_response.json()
                    user_id = order_data.get("user_id")
                    order_platform = order_data.get("order_platform", "telegram")
                    
                    # Получаем информацию о пользователе
                    user_tgid = None
                    user_vkid = None
                    if user_id:
                        try:
                            user_response = await client.get(
                                f"{USERS_SERVICE_URL}/users/{user_id}",
                                timeout=5.0
                            )
                            if user_response.status_code == 200:
                                user_data = user_response.json()
                                user_tgid = user_data.get("tgid")
                                user_vkid = user_data.get("vkid")
                        except Exception as e:
                            logger.warning(f"Не удалось получить информацию о пользователе {user_id}: {e}")
                    
                    # Если это первый платеж - отменяем все остальные платежи и заказ
                    if is_first_payment:
                        logger.info(f"Это первый платеж для заказа {payment.order_id}, отменяем все платежи и заказ. Был в холде: {was_holded}")
                        
                        # Отменяем все остальные платежи в холде для этого заказа
                        other_payments = (await session.execute(
                            select(Payment).where(
                                Payment.order_id == payment.order_id,
                                Payment.id != payment.id,
                                Payment.status == "waiting_for_capture"
                            )
                        )).scalars().all()
                        
                        for other_payment in other_payments:
                            try:
                                await cancel_payment(other_payment.yookassa_payment_id)
                                other_payment.status = "canceled"
                                other_payment.paid = False
                                await session.commit()
                                await session.refresh(other_payment)
                                logger.info(f"Платеж {other_payment.id} отменен из-за отмены первого платежа")
                            except Exception as e:
                                logger.error(f"Ошибка при отмене платежа {other_payment.id}: {e}", exc_info=True)
                        
                        cancel_reason = PAYMENT_CANCELED_ORDER_REASON
                        
                        # Проверяем текущий статус заказа перед отменой
                        # Если заказ уже отменен, не отправляем уведомление (избегаем дублирования)
                        current_order_status = order_data.get("status")
                        if current_order_status == "отменен":
                            logger.info(f"Заказ {payment.order_id} уже в статусе 'отменен', пропускаем отмену и уведомление")
                        else:
                            # Отменяем заказ через products-service
                            cancel_response = await client.post(
                                f"{PRODUCTS_SERVICE_URL}/internal/orders/{payment.order_id}/status",
                                json={
                                    "new_status": "отменен",
                                    "cancel_reason": cancel_reason,
                                    "restore_cart_items": True,
                                },
                                headers={"X-Internal-Token": INTERNAL_TOKEN},
                                timeout=10.0
                            )
                            
                            if cancel_response.status_code == 200:
                                logger.info(f"Заказ {payment.order_id} отменен из-за отмены первого платежа. Причина: {cancel_reason}")
                                waiver = (order_data.get("order_data") or {}).get("owner_payment_waiver")
                                waiver_applied = (
                                    isinstance(waiver, dict) and waiver.get("applied")
                                )
                                if not waiver_applied:
                                    zero_resp = await client.patch(
                                        f"{PRODUCTS_SERVICE_URL}/internal/orders/{payment.order_id}/paid-amount",
                                        json={"paid_amount": 0},
                                        headers={"X-Internal-Token": INTERNAL_TOKEN},
                                        timeout=10.0,
                                    )
                                    if zero_resp.status_code != 200:
                                        logger.warning(
                                            "Не удалось обнулить paid_amount заказа %s после отмены платежа: HTTP %s",
                                            payment.order_id,
                                            zero_resp.status_code,
                                        )
                                # Уведомляем пользователя об отмене заказа только если заказ был действительно отменен
                                # (не был отменен ранее)
                                text = (
                                    f"❌ Заказ #{payment.order_id} отменён.\n\n"
                                    f"{PAYMENT_CANCELED_ORDER_REASON}\n\n"
                                    f"{SUPPORT_VIA_CHANNEL_HINT}\n{MINIAPP_ORDERS_HINT}"
                                )
                                
                                if user_tgid:
                                    await _send_telegram_message(user_tgid, text)
                            else:
                                logger.warning(f"Не удалось отменить заказ {payment.order_id}: {cancel_response.status_code} - {cancel_response.text}")
                    else:
                        # Если не первый платеж - просто уведомляем
                        logger.info(f"Это не первый платеж для заказа {payment.order_id}, просто уведомляем пользователя")
                        
                        text = (
                            f"⚠️ Оплата по заказу #{payment.order_id} не прошла.\n\n"
                            f"Попробуй оплатить снова в мини-приложении.\n{MINIAPP_ORDERS_HINT}"
                        )
                        if user_tgid:
                            await _send_telegram_message(user_tgid, text)
                else:
                    logger.warning(f"Не удалось получить информацию о заказе {payment.order_id}: {order_response.status_code}")
        except Exception as e:
            logger.error(f"Ошибка при обработке отмены платежа: {e}", exc_info=True)
            # Не прерываем выполнение webhook

    try:
        db_pay = (
            await session.execute(select(Payment).where(Payment.id == payment.id))
        ).scalar_one_or_none()
        if db_pay:
            await sync_payment_status_from_yookassa(session, db_pay)
    except Exception as ex:
        logger.warning("ЮKassa webhook: досинхронизация чека/ОФД-ссылки: %s", ex)

    return {"status": "ok", "payment_id": payment.id}


async def _send_telegram_message(tgid: int, text: str) -> None:
    """Отправка сообщения пользователю в Telegram (API_BASE_URL/bot-api или прямой BOT_TOKEN)."""
    from api.shared import bot_api_client as _tg_bridge

    if not _tg_bridge.telegram_outbound_configured():
        logger.warning(
            "Нет исходящего Telegram (API_BASE_URL+bot-api или BOT_TOKEN) — уведомление не отправлено"
        )
        return
    await _tg_bridge.telegram_send_message(tgid, text, timeout=10.0)


async def capture_payment(payment_id: str) -> Dict[str, Any]:
    """Подтвердить платеж в ЮKassa (capture)"""
    if not YOOKASSA_SHOP_ID or not YOOKASSA_API_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ЮKassa не настроена. Проверьте YOOKASSA_SHOP_ID и YOOKASSA_API_TOKEN"
        )
    
    idempotence_key = str(uuid.uuid4())
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{YOOKASSA_API_URL}/{payment_id}/capture",
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_API_TOKEN),
                headers={
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json"
                },
                json={}  # Пустое тело для capture
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка при подтверждении платежа в ЮKassa: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Ошибка при подтверждении платежа: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Ошибка сети при подтверждении платежа: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка сети при подтверждении платежа: {str(e)}"
        )


async def cancel_payment(payment_id: str) -> Dict[str, Any]:
    """Отменить платеж в ЮKassa (cancel)"""
    if not YOOKASSA_SHOP_ID or not YOOKASSA_API_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ЮKassa не настроена. Проверьте YOOKASSA_SHOP_ID и YOOKASSA_API_TOKEN"
        )
    
    idempotence_key = str(uuid.uuid4())
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{YOOKASSA_API_URL}/{payment_id}/cancel",
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_API_TOKEN),
                headers={
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json"
                },
                json={}  # Пустое тело для cancel
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка при отмене платежа в ЮKassa: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Ошибка при отмене платежа: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Ошибка сети при отмене платежа: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка сети при отмене платежа: {str(e)}"
        )


@router.post("/internal/payments/capture-order-payments")
async def capture_order_payments(
    request: Dict[str, Any],
    _token_check = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session)
):
    """Подтвердить все платежи заказа в холде (capture) - вызывается при переходе из 'Выкуп' в 'в работе'"""
    order_id = request.get("order_id")
    if not order_id:
        raise HTTPException(status_code=400, detail="Не указан order_id")
    
    # Получаем все платежи заказа и подтверждаем их статус через ЮKassa
    all_payments = (await session.execute(
        select(Payment).where(
            Payment.order_id == order_id
        ).order_by(Payment.created_at.asc())
    )).scalars().all()
    
    for p in all_payments:
        await sync_payment_status_from_yookassa(session, p)
    logger.info(f"Заказ {order_id}: найдено {len(all_payments)} платежей. Статусы после синхронизации с ЮKassa: {[p.status for p in all_payments]}")
    
    # Платежи в холде — по актуальному статусу из ЮKassa
    payments = [p for p in all_payments if p.status == "waiting_for_capture"]
    
    if not payments:
        logger.warning(f"Нет платежей в холде (waiting_for_capture) для заказа {order_id}. Все платежи: {[(p.id, p.status, p.yookassa_payment_id) for p in all_payments]}")
        return {"status": "no_payments", "message": "Нет платежей в холде"}
    
    captured_count = 0
    errors = []
    
    for payment in payments:
        try:
            logger.info(f"Подтверждаем платеж {payment.id} (Yookassa ID: {payment.yookassa_payment_id}) для заказа {order_id}")
            yookassa_data = await capture_payment(payment.yookassa_payment_id)
            payment.status = yookassa_data.get("status", payment.status)
            payment.paid = yookassa_data.get("paid", payment.paid)
            if payment.paid and not payment.paid_at:
                captured_at = yookassa_data.get("captured_at")
                if captured_at:
                    payment.paid_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            await session.commit()
            await session.refresh(payment)
            await sync_payment_status_from_yookassa(session, payment)
            captured_count += 1
            logger.info(f"Платеж {payment.id} подтвержден (capture). Новый статус: {payment.status}, paid: {payment.paid}")
        except HTTPException as e:
            # Если платеж уже подтвержден, это не ошибка
            if "already" in str(e.detail).lower() or "captured" in str(e.detail).lower():
                logger.info(f"Платеж {payment.id} уже подтвержден в Yookassa")
                # Обновляем статус в БД
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(
                            f"{YOOKASSA_API_URL}/{payment.yookassa_payment_id}",
                            auth=(YOOKASSA_SHOP_ID, YOOKASSA_API_TOKEN),
                            headers={"Content-Type": "application/json"}
                        )
                        if response.status_code == 200:
                            yookassa_data = response.json()
                            payment.status = yookassa_data.get("status", payment.status)
                            payment.paid = yookassa_data.get("paid", payment.paid)
                            if payment.paid and not payment.paid_at:
                                captured_at = yookassa_data.get("captured_at")
                                if captured_at:
                                    payment.paid_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
                            await session.commit()
                            await session.refresh(payment)
                            await sync_payment_status_from_yookassa(session, payment)
                            captured_count += 1
                            logger.info(f"Статус платежа {payment.id} обновлен: {payment.status}")
                except Exception as update_error:
                    logger.error(f"Ошибка при обновлении статуса платежа {payment.id}: {update_error}", exc_info=True)
                    errors.append(f"Платеж {payment.id}: уже подтвержден, но не удалось обновить статус")
            else:
                errors.append(f"Платеж {payment.id}: {str(e.detail)}")
                logger.error(f"Ошибка при подтверждении платежа {payment.id}: {e.detail}", exc_info=True)
        except Exception as e:
            errors.append(f"Платеж {payment.id}: {str(e)}")
            logger.error(f"Ошибка при подтверждении платежа {payment.id}: {e}", exc_info=True)
    
    return {
        "status": "success" if not errors else "partial",
        "captured_count": captured_count,
        "total_count": len(payments),
        "errors": errors
    }


@router.post("/internal/payments/cancel-order-payments")
async def cancel_order_payments(
    request: Dict[str, Any],
    _token_check = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session)
):
    """Отменить все платежи заказа в холде (cancel) - вызывается при переходе в 'отменен'. Статус берётся из ЮKassa."""
    order_id = request.get("order_id")
    if not order_id:
        raise HTTPException(status_code=400, detail="Не указан order_id")
    
    # Загружаем все платежи заказа и синхронизируем статус с ЮKassa
    all_payments = (await session.execute(
        select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.asc())
    )).scalars().all()
    for p in all_payments:
        await sync_payment_status_from_yookassa(session, p)
    payments = [p for p in all_payments if p.status == "waiting_for_capture"]
    
    if not payments:
        logger.info(f"Нет платежей в холде для заказа {order_id}")
        return {"status": "no_payments", "message": "Нет платежей в холде"}
    
    canceled_count = 0
    errors = []
    
    for payment in payments:
        try:
            yookassa_data = await cancel_payment(payment.yookassa_payment_id)
            payment.status = yookassa_data.get("status", payment.status)
            payment.paid = yookassa_data.get("paid", payment.paid)
            await session.commit()
            await session.refresh(payment)
            canceled_count += 1
            logger.info(f"Платеж {payment.id} отменен (cancel)")
        except Exception as e:
            errors.append(f"Платеж {payment.id}: {str(e)}")
            logger.error(f"Ошибка при отмене платежа {payment.id}: {e}", exc_info=True)
    
    return {
        "status": "success" if not errors else "partial",
        "canceled_count": canceled_count,
        "total_count": len(payments),
        "errors": errors
    }


async def create_refund_yookassa(yookassa_payment_id: str, amount: Decimal) -> Dict[str, Any]:
    """Создать возврат в ЮKassa по платежу (полный или частичный)."""
    if not YOOKASSA_SHOP_ID or not YOOKASSA_API_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ЮKassa не настроена. Проверьте YOOKASSA_SHOP_ID и YOOKASSA_API_TOKEN"
        )
    value_str = f"{float(amount):.2f}"
    idempotence_key = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                YOOKASSA_REFUNDS_URL,
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_API_TOKEN),
                headers={
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json"
                },
                json={
                    "payment_id": yookassa_payment_id,
                    "amount": {"value": value_str, "currency": "RUB"}
                }
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"ЮKassa возврат создан: id={data.get('id')}, amount={value_str} RUB")
            return data
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка ЮKassa при создании возврата: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Ошибка возврата в ЮKassa: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Ошибка сети при создании возврата: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сети при возврате: {str(e)}")


class RefundOrderRequest(BaseModel):
    """Запрос на возврат по заказу"""
    order_id: int
    amount: Optional[Decimal] = None  # Если не указана — возвращаем всю внесённую сумму (по succeeded платежам)
    reason: Optional[str] = None  # Причина: вещь возвращена и т.д.


@router.post("/internal/refunds/order")
async def refund_order_payments(
    request: RefundOrderRequest,
    _token_check = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session)
):
    """
    Выполнить возврат по заказу (после списания или для завершённого заказа).
    Статус платежей подтверждается через API ЮKassa; возврат по успешным (succeeded) платежам.
    """
    order_id = request.order_id
    result = await session.execute(
        select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.asc())
    )
    all_payments = result.scalars().all()
    for p in all_payments:
        await sync_payment_status_from_yookassa(session, p)
    payments = [p for p in all_payments if p.status == "succeeded" and p.paid]
    if not payments:
        raise HTTPException(
            status_code=400,
            detail="Нет успешно проведённых платежей по заказу для возврата"
        )
    total_available = sum(float(p.amount) for p in payments)
    refund_amount = request.amount
    if refund_amount is None or refund_amount <= 0:
        refund_amount = Decimal(str(total_available))
    else:
        refund_amount = Decimal(str(refund_amount))
    if float(refund_amount) > total_available:
        raise HTTPException(
            status_code=400,
            detail=f"Сумма возврата {float(refund_amount):.2f} ₽ больше суммы платежей ({total_available:.2f} ₽)"
        )
    reason = (request.reason or "").strip() or "Возврат по заказу"
    remaining = float(refund_amount)
    refunded_total = Decimal("0")
    logs_created = []
    for payment in payments:
        if remaining <= 0:
            break
        if not payment.yookassa_payment_id:
            continue
        pay_amount = float(payment.amount)
        to_refund_here = min(remaining, pay_amount)
        if to_refund_here < 0.01:
            continue
        try:
            data = await create_refund_yookassa(payment.yookassa_payment_id, Decimal(str(round(to_refund_here, 2))))
            refund_id_yookassa = data.get("id")
            log = RefundLog(
                order_id=order_id,
                payment_id=payment.id,
                amount=Decimal(str(round(to_refund_here, 2))),
                reason=reason,
                yookassa_refund_id=refund_id_yookassa
            )
            session.add(log)
            await session.commit()
            refunded_total += log.amount
            logs_created.append({"payment_id": payment.id, "amount": float(log.amount), "yookassa_refund_id": refund_id_yookassa})
            remaining -= to_refund_here
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка при возврате по платежу {payment.id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка при возврате: {str(e)}")
    logger.info(f"По заказу {order_id} выполнен возврат на сумму {float(refunded_total):.2f} ₽. Причина: {reason}. Логов: {len(logs_created)}")
    return {
        "status": "ok",
        "order_id": order_id,
        "refunded_amount": float(refunded_total),
        "reason": reason,
        "refunds": logs_created
    }


async def _send_vk_message(vkid: int, text: str) -> None:
    """Отправка сообщения пользователю в VK"""
    vk_bot_token = getenv("VK_BOT_TOKEN")
    if not vk_bot_token:
        logger.warning("VK_BOT_TOKEN не указан, уведомление не отправлено")
        return
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.vk.com/method/messages.send",
                params={
                    "access_token": vk_bot_token,
                    "user_id": vkid,
                    "message": text,
                    "v": "5.131",
                    "random_id": 0
                }
            )
            response.raise_for_status()
            logger.info(f"Уведомление отправлено пользователю VK {vkid}")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления пользователю VK {vkid}: {e}", exc_info=True)

