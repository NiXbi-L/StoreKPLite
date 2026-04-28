"""
Роутер для заказов
"""
import copy
import json
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, Header, UploadFile, File, Form, Request
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from api.products.database.database import get_session
from api.products.models.order import Order
from api.products.models.cart import Cart
from api.products.models.item import Item
from api.products.models.order_delivery import OrderDelivery
from api.products.models.delivery_status import DeliveryStatus
from api.products.models.item_stock import ItemStock
from api.products.models.item_reservation import ItemReservation
from api.products.models.item_photo import ItemPhoto
from api.products.models.item_review import ItemReview, ItemReviewPhoto
from api.products.models.promocode import Promocode
from sqlalchemy import and_, func
from api.shared.auth import (
    get_user_id_for_request,
    get_profile_phone,
    get_jwt_admin_type_optional_from_request,
)
from sqlalchemy.orm import joinedload, selectinload
from decimal import Decimal
import httpx
import os
import logging

from api.products.utils.finance_context import (
    get_finance_price_context,
    FinancePriceContext,
    finance_price_context_for_owner_checkout,
)
from api.products.utils.item_pricing import compute_item_unit_price_for_ctx
logger = logging.getLogger(__name__)

FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://finance-service:8003")
DELIVERY_SERVICE_URL = os.getenv("DELIVERY_SERVICE_URL", "http://delivery-service:8005")
USERS_SERVICE_URL = os.getenv("USERS_SERVICE_URL", "http://users-service:8001")
_DEFAULT_INTERNAL_TOKEN = "internal-secret-token-change-in-production"
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", _DEFAULT_INTERNAL_TOKEN)
if INTERNAL_TOKEN == _DEFAULT_INTERNAL_TOKEN:
    logger.warning(
        "INTERNAL_TOKEN не задан — используется значение по умолчанию. "
        "В проде задайте INTERNAL_TOKEN в окружении."
    )
UPLOAD_DIR_REVIEWS = Path("uploads/reviews")
UPLOAD_DIR_REVIEWS.mkdir(parents=True, exist_ok=True)
MAX_REVIEW_PHOTOS = 10
MAX_REVIEW_PHOTO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB на файл
ALLOWED_REVIEW_PHOTO_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

router = APIRouter()

# Приём новых заказов (чекаут и POST /orders). Выключить: ORDER_CHECKOUT_DISABLED=0|false в окружении.
_ORDER_CHECKOUT_DISABLED_RAW = (os.getenv("ORDER_CHECKOUT_DISABLED", "true") or "").strip().lower()
ORDER_CHECKOUT_DISABLED = _ORDER_CHECKOUT_DISABLED_RAW in ("1", "true", "yes", "on")


def _raise_if_order_checkout_disabled() -> None:
    if not ORDER_CHECKOUT_DISABLED:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "code": "checkout_disabled",
            "message": "Приём заказов временно приостановлен.",
        },
    )


from api.products.utils.order_helpers import (
    cdek_delivery_calc_insurance_extras,
    compute_order_total,
    compute_order_amount_due,
    line_totals_for_order_items,
    sum_yookassa_receipt_items_rub,
    adjust_yookassa_receipt_sum_to_target,
)
from api.products.utils.tryon_order_discount import (
    reserve_tryon_for_order,
    preview_tryon_discount,
    release_tryon_for_order,
    complete_tryon_for_order,
    scale_commodity_line_totals,
)
from api.products.utils.parcel import build_line_items_for_parcel, aggregate_parcel_dimensions
from api.products.utils.promo_apply import (
    apply_promo_to_checkout_lines,
    delete_promo_redemptions_for_order,
    record_promo_redemptions_for_order,
)
from api.products.utils.referral_service_fee import sum_order_lines_service_fee_base_rub


async def _apply_tryon_discount_reservation_for_order(order: Order, user_id: int) -> None:
    """После flush заказа: резерв в users-service. Пропуск, если в finance не задана цена примерки."""
    if not user_id:
        return
    goods = Decimal(str(compute_order_total(order.order_data, exclude_returned=False) or 0))
    if goods <= 0:
        return
    try:
        res = await reserve_tryon_for_order(order.id, user_id, order.order_data or {}, goods)
    except Exception as e:
        logger.exception("Резерв скидки за примерки order_id=%s: %s", order.id, e)
        raise HTTPException(
            status_code=502,
            detail="Не удалось оформить скидку за примерки. Попробуйте позже.",
        )
    if not res:
        return
    order.tryon_discount_rub = Decimal(str(res["discount_rub"]))
    order.tryon_discount_units_reserved = int(res["units_reserved"])
    order.tryon_discount_bonus_credits = int(res["bonus_credits_on_complete"])


async def _get_reviewable_item_ids(
    session: AsyncSession, order: Order, user_id: int
) -> List[int]:
    """Товары заказа (уникальные item_id без возвращённых), на которые пользователь ещё не оставил отзыв. Только для статуса «завершен»."""
    if order.status != "завершен":
        return []
    items = (order.order_data or {}).get("items") or []
    item_ids_in_order = set()
    for item in items:
        if item.get("returned"):
            continue
        iid = item.get("item_id")
        if iid is not None:
            item_ids_in_order.add(iid)
    if not item_ids_in_order:
        return []
    result = await session.execute(
        select(ItemReview.item_id).where(
            ItemReview.user_id == user_id,
            ItemReview.item_id.in_(item_ids_in_order),
        )
    )
    reviewed_ids = set(result.scalars().all())
    return list(item_ids_in_order - reviewed_ids)


async def _enrich_order_data_with_photos(session: AsyncSession, order_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Добавляет в каждую позицию order_data['items'] поле photo (каталог — первое фото; кастом — сохранённый путь)."""
    if not order_data or not isinstance(order_data, dict):
        return order_data or {}
    items = order_data.get("items") or []
    if not items:
        return order_data
    item_ids = [item.get("item_id") for item in items if item.get("item_id") is not None]
    first_photo_by_item: Dict[int, str] = {}
    if item_ids:
        photos_result = await session.execute(
            select(ItemPhoto)
            .where(ItemPhoto.item_id.in_(item_ids))
            .order_by(ItemPhoto.item_id, func.coalesce(ItemPhoto.sort_order, 999999).asc(), ItemPhoto.id)
        )
        photos = photos_result.scalars().all()
        for p in photos:
            if p.item_id not in first_photo_by_item and p.file_path:
                first_photo_by_item[p.item_id] = p.file_path
    enriched_items = []
    for item in items:
        if not isinstance(item, dict):
            enriched_items.append(item)
            continue
        custom_photo = item.get("photo")
        catalog_photo = first_photo_by_item.get(item.get("item_id")) if item.get("item_id") is not None else None
        merged_photo = catalog_photo or (custom_photo if isinstance(custom_photo, str) and custom_photo.strip() else None)
        enriched_items.append({**item, "photo": merged_photo})
    return {**order_data, "items": enriched_items}


def _build_delivery_description_for_receipt(method_code: Optional[str]) -> str:
    """Человекочитаемое описание типа доставки для позиции чека."""
    if not method_code:
        return "Доставка"
    code = str(method_code).strip().upper()
    if code == "CDEK":
        return "Доставка CDEK"
    if code == "CDEK_MANUAL":
        return "Доставка (адрес вручную, СДЭК)"
    if code in ("COURIER_LOCAL", "LOCAL_COURIER"):
        return "Доставка курьером"
    if code in ("PICKUP_LOCAL", "LOCAL_PICKUP_POINT"):
        return "Доставка в пункт выдачи"
    return "Доставка"


def check_internal_token(token: Optional[str] = None) -> bool:
    """Проверка внутреннего токена для межсервисного взаимодействия"""
    if not token:
        return False
    clean_token = token.replace("Bearer ", "").strip() if token.startswith("Bearer") else token.strip()
    return clean_token == INTERNAL_TOKEN




async def calculate_item_price(item: Item, ctx: FinancePriceContext) -> Decimal:
    """StoreKPLite: фиксированная цена в рублях (без динамических формул)."""
    fixed = getattr(item, "fixed_price", None)
    if fixed is not None:
        return Decimal(str(fixed)).quantize(Decimal("0.01"))
    return Decimal(str(item.price)).quantize(Decimal("0.01"))


async def _get_available_stock(item_id: int, size: str, session: AsyncSession) -> int:
    """StoreKPLite: складской учёт отключён, считаем товар доступным."""
    _ = (item_id, size, session)
    return 10**9


async def _reserve_items_for_order(
    order_id: int,
    user_id: int,
    items_list: List[Dict[str, Any]],
    session: AsyncSession
) -> None:
    """StoreKPLite: резервирование отключено."""
    _ = (order_id, user_id, items_list, session)
    return None


async def _release_reservations_for_order(order_id: int, session: AsyncSession) -> None:
    """StoreKPLite: складские резервы отключены."""
    _ = (order_id, session)
    return None


async def _restore_order_lines_to_user_cart(
    session: AsyncSession,
    user_id: int,
    order: Order,
) -> None:
    """
    Вернуть состав заказа в корзину пользователя (системная отмена).
    Позиции с returned не возвращаем. Для in_stock учитываем доступный остаток после снятия резерва.
    """
    od = order.order_data or {}
    items = od.get("items") if isinstance(od, dict) else None
    if not items or not isinstance(items, list):
        return
    for row in items:
        if not isinstance(row, dict):
            continue
        if row.get("returned"):
            continue
        raw_id = row.get("item_id")
        if raw_id is None:
            continue
        try:
            item_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        qty = int(row.get("quantity") or 0)
        if qty <= 0:
            continue
        it = await session.get(Item, item_id)
        if not it:
            logger.warning("restore_cart: товар id=%s не найден, позиция пропущена", item_id)
            continue
        st = row.get("stock_type") or "preorder"
        if st not in ("preorder", "in_stock"):
            st = "preorder"
        size = row.get("size")
        if st == "in_stock":
            size_val = (size or "").strip() if size is not None else ""
            if not size_val:
                logger.warning("restore_cart: in_stock без размера item_id=%s, пропуск", item_id)
                continue
            available = await _get_available_stock(item_id, size_val, session)
            add_qty = min(qty, max(0, available))
            if add_qty <= 0:
                logger.warning(
                    "restore_cart: нет доступного количества item_id=%s size=%s (запрошено %s)",
                    item_id,
                    size_val,
                    qty,
                )
                continue
            existing = (
                await session.execute(
                    select(Cart).where(
                        and_(
                            Cart.user_id == user_id,
                            Cart.item_id == item_id,
                            Cart.size == size,
                            Cart.stock_type == st,
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing:
                total = existing.quantity + add_qty
                existing.quantity = min(total, available)
            else:
                session.add(
                    Cart(
                        user_id=user_id,
                        item_id=item_id,
                        size=size,
                        quantity=min(add_qty, available),
                        stock_type=st,
                    )
                )
        else:
            existing = (
                await session.execute(
                    select(Cart).where(
                        and_(
                            Cart.user_id == user_id,
                            Cart.item_id == item_id,
                            Cart.size == size,
                            Cart.stock_type == st,
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.quantity += qty
            else:
                session.add(
                    Cart(
                        user_id=user_id,
                        item_id=item_id,
                        size=size,
                        quantity=qty,
                        stock_type=st,
                    )
                )


async def _convert_reservations_to_deduction(order_id: int, session: AsyncSession) -> None:
    """StoreKPLite: списание склада отключено."""
    _ = (order_id, session)
    return None


async def _check_stock_availability(cart_items: List[Cart], session: AsyncSession) -> tuple[bool, List[Dict[str, Any]]]:
    """StoreKPLite: склад отключен, проверка наличия не применяется."""
    _ = (cart_items, session)
    return True, []


async def _decrease_stock_quantities(order: Order, session: AsyncSession):
    """Для чекаута списание не делаем при создании заказа — только резерв. Старый create_order не списывает."""
    pass


async def _increase_stock_quantities(order: Order, session: AsyncSession):
    """При отмене заказа со склада снимаем резерв (_release_reservations_for_order), остатки не трогаем."""
    await _release_reservations_for_order(order.id, session)


class CreateOrderRequest(BaseModel):
    order_data: Optional[Dict[str, Any]] = None  # JSON данные заказа
    phone_number: Optional[str] = None
    order_type: Optional[str] = None  # "preorder", "in_stock" или None (все товары, но создаем один заказ)


class CheckoutCreateRequest(BaseModel):
    """Создание заказа из чекаута: выбранные позиции корзины + контакт и зафиксированные данные доставки."""
    cart_item_ids: List[int]
    recipient_name: Optional[str] = None
    phone_number: Optional[str] = None
    # Если задан delivery_preset_id, адрес/ПВЗ/способ подтягиваются из delivery-service (тело доставки не доверяем).
    delivery_preset_id: Optional[int] = None
    delivery_address: Optional[str] = None
    delivery_postal_code: Optional[str] = None
    delivery_city_code: Optional[int] = None
    delivery_cost_rub: Optional[float] = None
    delivery_method_code: Optional[str] = None  # "CDEK", "COURIER_LOCAL" и т.д. — для кнопки «Создать накладную»
    cdek_delivery_point_code: Optional[str] = None  # код ПВЗ СДЭК из пресета (delivery_point в API СДЭК)
    promo_code: Optional[str] = None


class CheckoutCreateResponse(BaseModel):
    order_id: int
    order_total_rub: float
    delivery_cost_rub: Optional[float] = None  # рассчитано на беке; фронт только для отображения
    tryon_discount_rub: float = 0.0
    goods_after_tryon_rub: float = 0.0  # товары минус скидка за примерки (без доставки)
    payable_total_rub: float = 0.0  # к оплате: товары - скидка + доставка
    promo_discount_rub: float = 0.0
    # owner_waiver: только JWT с claim admin_type == «owner» (владелец). Сотрудники (staff) и прочие admin_type не получают.
    owner_waiver: bool = False


class CheckoutPreviewResponse(BaseModel):
    order_total_rub: float
    delivery_cost_rub: Optional[float] = None
    tryon_discount_rub: float = 0.0
    goods_after_tryon_rub: float = 0.0
    payable_total_rub: float = 0.0
    promo_discount_rub: float = 0.0
    owner_waiver: bool = False


async def _fetch_checkout_delivery_preset_snapshot(user_id: int, preset_id: int) -> Dict[str, Any]:
    """Снимок пресета из delivery-service (internal)."""
    url = f"{DELIVERY_SERVICE_URL.rstrip('/')}/internal/user-delivery-data/checkout-snapshot"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            url,
            params={"user_id": user_id, "preset_id": preset_id},
            headers={"X-Internal-Token": INTERNAL_TOKEN},
        )
    if resp.status_code == 404:
        raise HTTPException(
            status_code=400,
            detail="Сохранённый адрес доставки не найден или не принадлежит пользователю",
        )
    if resp.status_code != 200:
        logger.warning(
            "checkout preset snapshot: delivery HTTP %s %s",
            resp.status_code,
            (resp.text or "")[:500],
        )
        raise HTTPException(status_code=502, detail="Не удалось получить данные доставки")
    return resp.json()


async def _checkout_effective_delivery(user_id: int, request: CheckoutCreateRequest) -> Dict[str, Any]:
    """
    Итоговые поля доставки и контакта для чекаута.
    При delivery_preset_id данные доставки только из БД delivery (без подмены с клиента).
    """
    if request.delivery_preset_id is None:
        return {
            "delivery_address": request.delivery_address,
            "delivery_postal_code": request.delivery_postal_code,
            "delivery_city_code": request.delivery_city_code,
            "delivery_method_code": (request.delivery_method_code or "").strip() or None,
            "cdek_delivery_point_code": request.cdek_delivery_point_code,
            "recipient_name": request.recipient_name,
            "phone_number": request.phone_number,
        }
    p = await _fetch_checkout_delivery_preset_snapshot(user_id, request.delivery_preset_id)
    return {
        "delivery_address": p.get("address"),
        "delivery_postal_code": p.get("postal_code"),
        "delivery_city_code": p.get("city_code"),
        "delivery_method_code": (p.get("delivery_method_code") or "").strip() or None,
        "cdek_delivery_point_code": p.get("cdek_delivery_point_code"),
        "recipient_name": p.get("recipient_name") or request.recipient_name,
        "phone_number": p.get("phone_number") or request.phone_number,
    }


async def _apply_owner_waiver_order_payment(session: AsyncSession, order: Order, amount_due: float) -> None:
    """
    Оплата заказа только владельцем (JWT admin_type строго owner, не staff) без ЮKassa: 100% «скидка»,
    paid_amount = сумме к оплате, статус как после успешного платежа (webhook finance).
    """
    order.paid_amount = Decimal(str(round(float(amount_due), 2)))
    od = dict(order.order_data or {})
    w = od.get("owner_payment_waiver")
    if not isinstance(w, dict):
        w = {}
    w["percent"] = 100
    w["applied"] = True
    od["owner_payment_waiver"] = w
    order.order_data = od
    flag_modified(order, "order_data")
    st = (order.status or "").strip()
    if not order.is_from_stock and st == "Ожидает":
        order.status = "Выкуп"


class CreatePaymentForOrderRequest(BaseModel):
    """Запрос на создание платежа по заказу (прокси в finance). Сумма к оплате считается на беке."""
    return_url: str


class DeliveryInfo(BaseModel):
    """Информация о доставке"""
    status_name: Optional[str] = None
    additional_info: Optional[str] = None
    updated_at: Optional[datetime] = None


class OrderResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    order_data: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    paid_amount: float
    order_total: Optional[float] = None  # к оплате: товары - скидка за примерки + доставка
    delivery: Optional[DeliveryInfo] = None
    recipient_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_from_stock: bool = False
    tracking_number: Optional[str] = None
    tryon_discount_rub: float = 0.0
    # Для статуса «завершен»: item_id товаров заказа, на которые пользователь ещё не оставил отзыв
    reviewable_item_ids: Optional[List[int]] = None

    class Config:
        from_attributes = True


@router.post("/orders", response_model=OrderResponse)
async def create_order(
    order_req: CreateOrderRequest,
    http_request: Request,
    user_id: int = Depends(get_user_id_for_request),
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session)
):
    """Создать заказ из корзины и привязать к пользователю"""
    _raise_if_order_checkout_disabled()
    # Получаем товары из корзины
    cart_result = await session.execute(
        select(Cart).where(Cart.user_id == user_id)
    )
    cart_items = cart_result.scalars().all()
    
    if not cart_items:
        raise HTTPException(status_code=400, detail="Корзина пуста")
    
    # Разделяем товары на предзаказ и со склада
    preorder_items = [item for item in cart_items if item.stock_type == "preorder"]
    in_stock_items = [item for item in cart_items if item.stock_type == "in_stock"]
    
    # Если указан order_type, фильтруем товары
    order_type = order_req.order_type
    if order_type == "preorder":
        # Создаем заказ только для предзаказа
        in_stock_items = []
    elif order_type == "in_stock":
        # Создаем заказ только для наличия
        preorder_items = []
    # Если order_type не указан или "all" - создаем заказ для всех товаров (но один заказ, не два)
    
    # Получаем актуальный курс и стоимость доставки одним запросом к finance
    jwt_admin_type = await get_jwt_admin_type_optional_from_request(http_request, authorization)
    ctx = await get_finance_price_context()
    if jwt_admin_type == "owner":
        ctx = finance_price_context_for_owner_checkout(ctx)

    # Формируем данные заказа для предзаказа
    preorder_order_items = []
    for cart_item in preorder_items:
        item_result = await session.execute(
            select(Item).where(Item.id == cart_item.item_id)
        )
        item = item_result.scalar_one_or_none()
        if item:
            # Рассчитываем актуальную цену в рублях на момент создания заказа
            price_rub = await calculate_item_price(item, ctx)
            
            preorder_order_items.append({
                "item_id": item.id,
                "name": item.name,
                "chinese_name": getattr(item, "chinese_name", None),
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "price": float(price_rub),  # Сохраняем актуальную цену в рублях
                "link": item.link,
                "stock_type": "preorder"
            })
    
    # ПРОВЕРЯЕМ НАЛИЧИЕ товаров со склада перед созданием заказа
    if in_stock_items:
        all_available, unavailable_items = await _check_stock_availability(in_stock_items, session)
        
        if not all_available:
            # Возвращаем ошибку с информацией о товарах, которых нет в наличии
            error_detail = {
                "error": "Не все товары в наличии",
                "unavailable_items": unavailable_items,
                "message": f"Некоторые товары отсутствуют в наличии. Товаров не хватает: {len(unavailable_items)}"
            }
            raise HTTPException(status_code=400, detail=error_detail)
    
    # Формируем данные заказа для товаров со склада
    in_stock_order_items = []
    for cart_item in in_stock_items:
        item_result = await session.execute(
            select(Item).where(Item.id == cart_item.item_id)
        )
        item = item_result.scalar_one_or_none()
        if item:
            price_rub = float(await calculate_item_price(item, ctx))
            in_stock_order_items.append({
                "item_id": item.id,
                "name": item.name,
                "chinese_name": getattr(item, "chinese_name", None),
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "price": price_rub,
                "link": item.link,
                "stock_type": "in_stock"
            })
    
    # Создаем один заказ из выбранных товаров
    # Объединяем товары в один заказ (если есть оба типа - создаем один заказ со всеми товарами)
    all_order_items = []
    has_in_stock = len(in_stock_order_items) > 0
    
    # Добавляем товары по предзаказу
    all_order_items.extend(preorder_order_items)
    
    # Добавляем товары из наличия
    all_order_items.extend(in_stock_order_items)
    
    if not all_order_items:
        raise HTTPException(status_code=400, detail="Нет товаров для создания заказа")
    
    # Определяем статус заказа: если есть товары из наличия, статус "в работе", иначе "Ожидает"
    order_status = "в работе" if has_in_stock else "Ожидает"
    
    # Телефон: из запроса или из профиля пользователя
    phone_for_order = (order_req.phone_number or "").strip() or None
    if not phone_for_order:
        phone_for_order = await get_profile_phone(user_id)
    
    # Создаем заказ
    order_data_dict = {"items": all_order_items}
    order = Order(
        user_id=user_id,
        order_data=order_data_dict,
        status=order_status,
        phone_number=phone_for_order,
        is_from_stock=has_in_stock
    )
    session.add(order)
    try:
        await session.flush()
        await session.refresh(order)
        await _apply_tryon_discount_reservation_for_order(order, user_id)
        # СПИСЫВАЕМ товары со склада сразу после создания заказа, если они есть
        if has_in_stock:
            await _decrease_stock_quantities(order, session)
            logger.info(f"Товары списаны со склада для заказа {order.id}")
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    
    # Очищаем корзину только для товаров, которые были включены в заказ
    items_to_delete = []
    if order_type == "preorder":
        items_to_delete = preorder_items
    elif order_type == "in_stock":
        items_to_delete = in_stock_items
    else:
        # Удаляем все товары (заказ для всех товаров)
        items_to_delete = cart_items
    
    for cart_item in items_to_delete:
        await session.delete(cart_item)
    await session.commit()
    
    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        order_data=order.order_data,
        status=order.status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        paid_amount=float(order.paid_amount),
        order_total=compute_order_amount_due(
            order.order_data,
            float(getattr(order, "tryon_discount_rub", 0) or 0),
            float(((order.order_data or {}).get("delivery_snapshot") or {}).get("delivery_cost_rub") or 0),
            exclude_returned=False,
        ),
        phone_number=order.phone_number,
        is_from_stock=order.is_from_stock,
        tracking_number=getattr(order, "tracking_number", None),
        tryon_discount_rub=float(getattr(order, "tryon_discount_rub", 0) or 0),
    )


@router.post("/orders/checkout", response_model=CheckoutCreateResponse)
async def checkout_create_order(
    request: CheckoutCreateRequest,
    http_request: Request,
    user_id: int = Depends(get_user_id_for_request),
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session)
):
    """Создать заказ из выбранных позиций корзины (чекаут). Товары со склада резервируются."""
    _raise_if_order_checkout_disabled()
    if not request.cart_item_ids:
        raise HTTPException(status_code=400, detail="Укажите позиции корзины")
    cart_result = await session.execute(
        select(Cart).where(
            Cart.user_id == user_id,
            Cart.id.in_(request.cart_item_ids)
        )
    )
    cart_items = cart_result.scalars().all()
    if len(cart_items) != len(request.cart_item_ids):
        raise HTTPException(status_code=400, detail="Не все выбранные позиции найдены в корзине")
    d_eff = await _checkout_effective_delivery(user_id, request)
    preorder_items = [c for c in cart_items if getattr(c, "stock_type", None) == "preorder"]
    in_stock_items = [c for c in cart_items if getattr(c, "stock_type", None) == "in_stock"]
    jwt_admin_type = await get_jwt_admin_type_optional_from_request(http_request, authorization)
    ctx = await get_finance_price_context()
    if jwt_admin_type == "owner":
        ctx = finance_price_context_for_owner_checkout(ctx)
    preorder_order_items = []
    for cart_item in preorder_items:
        item_result = await session.execute(select(Item).where(Item.id == cart_item.item_id))
        item = item_result.scalar_one_or_none()
        if item:
            price_rub = await calculate_item_price(item, ctx)
            preorder_order_items.append({
                "item_id": item.id,
                "name": item.name,
                "chinese_name": getattr(item, "chinese_name", None),
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "price": float(price_rub),
                "link": item.link,
                "stock_type": "preorder"
            })
    in_stock_order_items = []
    for cart_item in in_stock_items:
        item_result = await session.execute(select(Item).where(Item.id == cart_item.item_id))
        item = item_result.scalar_one_or_none()
        if item:
            price_rub = float(await calculate_item_price(item, ctx))
            in_stock_order_items.append({
                "item_id": item.id,
                "name": item.name,
                "chinese_name": getattr(item, "chinese_name", None),
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "price": price_rub,
                "link": item.link,
                "stock_type": "in_stock"
            })
    all_order_items = preorder_order_items + in_stock_order_items
    if not all_order_items:
        raise HTTPException(status_code=400, detail="Нет товаров для заказа")
    has_in_stock = len(in_stock_order_items) > 0
    order_status = "в работе" if has_in_stock else "Ожидает"

    # Для СДЭК страховки в калькуляторе нужна объявленная стоимость до промо (иначе при 100% скидке price=0).
    cdek_insurance_declared_lines = copy.deepcopy(all_order_items)

    checkout_lines = copy.deepcopy(all_order_items)
    promo_total_dec = Decimal("0")
    if request.promo_code and str(request.promo_code).strip():
        checkout_lines, promo_total_dec, promo_err = await apply_promo_to_checkout_lines(
            session,
            user_id,
            request.promo_code,
            checkout_lines,
            code_snapshot=str(request.promo_code).strip(),
            lock_promo_row=True,
            exchange_rate=ctx.rate_with_margin,
            delivery_cost_per_kg=ctx.delivery_cost_per_kg,
            yuan_markup_before_rub_percent=ctx.yuan_markup_before_rub_percent,
        )
        if promo_err:
            raise HTTPException(status_code=400, detail=promo_err)
    all_order_items = checkout_lines

    # Расчёт доставки на беке: габариты посылки и запрос к delivery-service (не доверяем фронту).
    delivery_cost_rub_calculated: Optional[float] = None
    cdek_tariff_code_calculated: Optional[int] = None
    item_ids = [row["item_id"] for row in all_order_items if row.get("item_id")]
    items_by_id: Dict[int, Any] = {}
    if item_ids:
        items_result = await session.execute(select(Item).where(Item.id.in_(item_ids)))
        for it in items_result.scalars().all():
            items_by_id[it.id] = it
    line_items = build_line_items_for_parcel(all_order_items, items_by_id)
    parcel = aggregate_parcel_dimensions(line_items)
    delivery_method_code = d_eff["delivery_method_code"]
    if delivery_method_code:
        try:
            calc_body: Dict[str, Any] = {
                "parcel": {
                    "weight_gram": parcel["weight_gram"],
                    "length_cm": parcel["length_cm"],
                    "width_cm": parcel["width_cm"],
                    "height_cm": parcel["height_cm"],
                },
                "delivery_method_code": delivery_method_code,
                "to_city_code": d_eff["delivery_city_code"],
                "to_city": (d_eff["delivery_address"] or "").strip() or None,
            }
            _cdek_dp = (str(d_eff.get("cdek_delivery_point_code") or "").strip())
            if _cdek_dp:
                calc_body["cdek_delivery_point_code"] = _cdek_dp
            calc_body.update(
                cdek_delivery_calc_insurance_extras(delivery_method_code, cdek_insurance_declared_lines)
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                calc_resp = await client.post(
                    f"{DELIVERY_SERVICE_URL}/calculate-cost",
                    json=calc_body,
                )
                if calc_resp.status_code == 200:
                    data = calc_resp.json()
                    if data.get("delivery_cost_rub") is not None:
                        delivery_cost_rub_calculated = float(data["delivery_cost_rub"])
                    tc = data.get("cdek_tariff_code")
                    if tc is not None:
                        try:
                            cdek_tariff_code_calculated = int(tc)
                        except (TypeError, ValueError):
                            pass
        except Exception as e:
            logger.warning("Не удалось рассчитать доставку при чекауте: %s", e)

    if delivery_method_code == "CDEK_MANUAL":
        delivery_cost_rub_calculated = None
        cdek_tariff_code_calculated = None

    order_data_dict: Dict[str, Any] = {"items": all_order_items}
    if float(promo_total_dec) > 0 and request.promo_code and str(request.promo_code).strip():
        order_data_dict["promo_snapshot"] = {
            "code_entered": str(request.promo_code).strip(),
            "discount_rub": float(promo_total_dec),
        }
        admin_pid: Optional[int] = None
        for row in all_order_items:
            raw_pid = row.get("promo_admin_id")
            if raw_pid is not None:
                admin_pid = int(raw_pid)
                break
        if admin_pid is not None:
            pc = await session.get(Promocode, admin_pid)
            if (
                pc
                and pc.referrer_user_id is not None
                and pc.referral_commission_percent is not None
                and float(pc.referral_commission_percent) > 0
            ):
                fee_base = await sum_order_lines_service_fee_base_rub(
                    session,
                    all_order_items,
                    ctx.rate_with_margin,
                    ctx.yuan_markup_before_rub_percent,
                )
                order_data_dict["referral_snapshot"] = {
                    "referrer_user_id": int(pc.referrer_user_id),
                    "promocode_id": int(pc.id),
                    "commission_percent": float(pc.referral_commission_percent),
                    "service_fee_base_rub": float(fee_base),
                }
    has_delivery_block = request.delivery_preset_id is not None or any(
        [
            request.delivery_address is not None,
            request.delivery_postal_code is not None,
            request.delivery_city_code is not None,
            request.delivery_method_code is not None,
            request.cdek_delivery_point_code is not None,
        ]
    )
    if has_delivery_block:
        snap_delivery: Dict[str, Any] = {
            "address": (d_eff["delivery_address"] or "").strip() or None,
            "postal_code": (d_eff["delivery_postal_code"] or "").strip() or None,
            "city_code": d_eff["delivery_city_code"],
            "delivery_cost_rub": delivery_cost_rub_calculated,
            "delivery_method_code": delivery_method_code,
        }
        if cdek_tariff_code_calculated is not None:
            snap_delivery["cdek_tariff_code"] = cdek_tariff_code_calculated
        dpv = (str(d_eff["cdek_delivery_point_code"] or "").strip())
        if dpv:
            snap_delivery["cdek_delivery_point_code"] = dpv
        if request.delivery_preset_id is not None:
            snap_delivery["delivery_preset_id"] = request.delivery_preset_id
        order_data_dict["delivery_snapshot"] = snap_delivery
    phone_for_order = (d_eff["phone_number"] or "").strip() or None
    if not phone_for_order:
        phone_for_order = await get_profile_phone(user_id)
    order = Order(
        user_id=user_id,
        order_data=order_data_dict,
        status=order_status,
        phone_number=phone_for_order,
        recipient_name=d_eff["recipient_name"],
        is_from_stock=has_in_stock
    )
    session.add(order)
    try:
        await session.flush()
        await session.refresh(order)
        await _apply_tryon_discount_reservation_for_order(order, user_id)
        if float(promo_total_dec) > 0 and request.promo_code and str(request.promo_code).strip():
            record_promo_redemptions_for_order(
                session,
                order.id,
                user_id,
                all_order_items,
                str(request.promo_code).strip(),
            )
        if has_in_stock:
            await _reserve_items_for_order(order.id, user_id, in_stock_order_items, session)
        for cart_item in cart_items:
            await session.delete(cart_item)
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    order_total = float(compute_order_total(order.order_data) or 0)
    tryon_d = float(getattr(order, "tryon_discount_rub", 0) or 0)
    # payable=0 и owner_waiver только при admin_type «owner» в JWT (см. jwt_admin_type выше).
    owner_waiver = jwt_admin_type == "owner"
    payable = compute_order_amount_due(
        order.order_data,
        tryon_d,
        float(delivery_cost_rub_calculated or 0),
        exclude_returned=False,
    )
    if owner_waiver:
        payable = 0.0
    return CheckoutCreateResponse(
        order_id=order.id,
        order_total_rub=order_total,
        delivery_cost_rub=delivery_cost_rub_calculated,
        tryon_discount_rub=tryon_d,
        goods_after_tryon_rub=float(round(max(0.0, order_total - tryon_d))),
        payable_total_rub=payable,
        promo_discount_rub=float(promo_total_dec),
        owner_waiver=owner_waiver,
    )


@router.post("/orders/checkout/preview", response_model=CheckoutPreviewResponse)
async def checkout_preview(
    request: CheckoutCreateRequest,
    http_request: Request,
    user_id: int = Depends(get_user_id_for_request),
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Предпросмотр скидок/итога на чекауте без создания заказа."""
    _raise_if_order_checkout_disabled()
    if not request.cart_item_ids:
        raise HTTPException(status_code=400, detail="Укажите позиции корзины")
    cart_result = await session.execute(
        select(Cart).where(
            Cart.user_id == user_id,
            Cart.id.in_(request.cart_item_ids)
        )
    )
    cart_items = cart_result.scalars().all()
    if len(cart_items) != len(request.cart_item_ids):
        raise HTTPException(status_code=400, detail="Не все выбранные позиции найдены в корзине")
    d_eff = await _checkout_effective_delivery(user_id, request)
    preorder_items = [c for c in cart_items if getattr(c, "stock_type", None) == "preorder"]
    in_stock_items = [c for c in cart_items if getattr(c, "stock_type", None) == "in_stock"]
    jwt_admin_type = await get_jwt_admin_type_optional_from_request(http_request, authorization)
    ctx = await get_finance_price_context()
    if jwt_admin_type == "owner":
        ctx = finance_price_context_for_owner_checkout(ctx)
    preorder_order_items = []
    for cart_item in preorder_items:
        item_result = await session.execute(select(Item).where(Item.id == cart_item.item_id))
        item = item_result.scalar_one_or_none()
        if item:
            price_rub = await calculate_item_price(item, ctx)
            preorder_order_items.append({
                "item_id": item.id,
                "name": item.name,
                "chinese_name": getattr(item, "chinese_name", None),
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "price": float(price_rub),
                "link": item.link,
                "stock_type": "preorder"
            })
    in_stock_order_items = []
    for cart_item in in_stock_items:
        item_result = await session.execute(select(Item).where(Item.id == cart_item.item_id))
        item = item_result.scalar_one_or_none()
        if item:
            price_rub = float(await calculate_item_price(item, ctx))
            in_stock_order_items.append({
                "item_id": item.id,
                "name": item.name,
                "chinese_name": getattr(item, "chinese_name", None),
                "quantity": cart_item.quantity,
                "size": cart_item.size,
                "price": price_rub,
                "link": item.link,
                "stock_type": "in_stock"
            })
    all_order_items = preorder_order_items + in_stock_order_items
    if not all_order_items:
        raise HTTPException(status_code=400, detail="Нет товаров для заказа")

    cdek_insurance_declared_lines = copy.deepcopy(all_order_items)

    preview_lines = copy.deepcopy(all_order_items)
    promo_preview_dec = Decimal("0")
    if request.promo_code and str(request.promo_code).strip():
        preview_lines, promo_preview_dec, promo_err = await apply_promo_to_checkout_lines(
            session,
            user_id,
            request.promo_code,
            preview_lines,
            code_snapshot=str(request.promo_code).strip(),
            exchange_rate=ctx.rate_with_margin,
            delivery_cost_per_kg=ctx.delivery_cost_per_kg,
            yuan_markup_before_rub_percent=ctx.yuan_markup_before_rub_percent,
        )
        if promo_err:
            raise HTTPException(status_code=400, detail=promo_err)
    all_order_items = preview_lines

    delivery_cost_rub_calculated: Optional[float] = None
    cdek_tariff_code_calculated: Optional[int] = None
    item_ids = [row["item_id"] for row in all_order_items if row.get("item_id")]
    items_by_id: Dict[int, Any] = {}
    if item_ids:
        items_result = await session.execute(select(Item).where(Item.id.in_(item_ids)))
        for it in items_result.scalars().all():
            items_by_id[it.id] = it
    line_items = build_line_items_for_parcel(all_order_items, items_by_id)
    parcel = aggregate_parcel_dimensions(line_items)
    delivery_method_code = d_eff["delivery_method_code"]
    if delivery_method_code:
        try:
            calc_body_pv: Dict[str, Any] = {
                "parcel": {
                    "weight_gram": parcel["weight_gram"],
                    "length_cm": parcel["length_cm"],
                    "width_cm": parcel["width_cm"],
                    "height_cm": parcel["height_cm"],
                },
                "delivery_method_code": delivery_method_code,
                "to_city_code": d_eff["delivery_city_code"],
                "to_city": (d_eff["delivery_address"] or "").strip() or None,
            }
            _cdek_dp_pv = (str(d_eff.get("cdek_delivery_point_code") or "").strip())
            if _cdek_dp_pv:
                calc_body_pv["cdek_delivery_point_code"] = _cdek_dp_pv
            calc_body_pv.update(
                cdek_delivery_calc_insurance_extras(delivery_method_code, cdek_insurance_declared_lines)
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                calc_resp = await client.post(
                    f"{DELIVERY_SERVICE_URL}/calculate-cost",
                    json=calc_body_pv,
                )
                if calc_resp.status_code == 200:
                    data = calc_resp.json()
                    if data.get("delivery_cost_rub") is not None:
                        delivery_cost_rub_calculated = float(data["delivery_cost_rub"])
                    tc = data.get("cdek_tariff_code")
                    if tc is not None:
                        try:
                            cdek_tariff_code_calculated = int(tc)
                        except (TypeError, ValueError):
                            pass
        except Exception as e:
            logger.warning("Не удалось рассчитать доставку при preview чекаута: %s", e)

    if delivery_method_code == "CDEK_MANUAL":
        delivery_cost_rub_calculated = None
        cdek_tariff_code_calculated = None

    order_data_dict: Dict[str, Any] = {"items": all_order_items}
    has_delivery_preview = request.delivery_preset_id is not None or any(
        [
            request.delivery_address is not None,
            request.delivery_postal_code is not None,
            request.delivery_city_code is not None,
            request.delivery_method_code is not None,
            request.cdek_delivery_point_code is not None,
        ]
    )
    if has_delivery_preview:
        snap_pv: Dict[str, Any] = {
            "address": (d_eff["delivery_address"] or "").strip() or None,
            "postal_code": (d_eff["delivery_postal_code"] or "").strip() or None,
            "city_code": d_eff["delivery_city_code"],
            "delivery_cost_rub": delivery_cost_rub_calculated,
            "delivery_method_code": delivery_method_code,
        }
        if cdek_tariff_code_calculated is not None:
            snap_pv["cdek_tariff_code"] = cdek_tariff_code_calculated
        dpv2 = (str(d_eff["cdek_delivery_point_code"] or "").strip())
        if dpv2:
            snap_pv["cdek_delivery_point_code"] = dpv2
        if request.delivery_preset_id is not None:
            snap_pv["delivery_preset_id"] = request.delivery_preset_id
        order_data_dict["delivery_snapshot"] = snap_pv

    goods = Decimal(str(compute_order_total(order_data_dict) or 0))
    item_units = sum(int(i.get("quantity") or 0) for i in all_order_items)
    preview = await preview_tryon_discount(user_id=user_id, item_units=item_units, goods_subtotal=goods)
    tryon_d = float(preview.get("discount_rub") or 0)
    order_total = float(compute_order_total(order_data_dict) or 0)
    owner_waiver = jwt_admin_type == "owner"  # только владелец, не любой админ
    payable_pv = compute_order_amount_due(
        order_data_dict,
        tryon_d,
        float(delivery_cost_rub_calculated or 0),
        exclude_returned=False,
    )
    if owner_waiver:
        payable_pv = 0.0
    return CheckoutPreviewResponse(
        order_total_rub=order_total,
        delivery_cost_rub=delivery_cost_rub_calculated,
        tryon_discount_rub=tryon_d,
        goods_after_tryon_rub=float(round(max(0.0, order_total - tryon_d))),
        payable_total_rub=payable_pv,
        promo_discount_rub=float(promo_preview_dec),
        owner_waiver=owner_waiver,
    )


@router.get("/orders", response_model=List[OrderResponse])
async def get_user_orders(
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Получить все заказы пользователя (скрытые не возвращаются). Итог без возвращённых позиций; состав обогащён фото."""
    result = await session.execute(
        select(Order)
        .options(joinedload(Order.delivery).joinedload(OrderDelivery.delivery_status))
        .where(Order.user_id == user_id, Order.hidden_from_user_at.is_(None))
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().unique().all()
    
    order_responses = []
    for order in orders:
        delivery_info = None
        if order.delivery:
            delivery_info = DeliveryInfo(
                status_name=order.delivery.delivery_status.name if order.delivery.delivery_status else None,
                additional_info=order.delivery.additional_info,
                updated_at=order.delivery.updated_at
            )
        enriched_data = await _enrich_order_data_with_photos(session, order.order_data)
        reviewable_ids = await _get_reviewable_item_ids(session, order, user_id) if order.status == "завершен" else None
        order_responses.append(OrderResponse(
            id=order.id,
            user_id=order.user_id,
            order_data=enriched_data,
            status=order.status,
            created_at=order.created_at,
            updated_at=order.updated_at,
            paid_amount=float(order.paid_amount),
            order_total=compute_order_amount_due(
                order.order_data,
                float(getattr(order, "tryon_discount_rub", 0) or 0),
                float(((order.order_data or {}).get("delivery_snapshot") or {}).get("delivery_cost_rub") or 0),
                exclude_returned=True,
            ),
            delivery=delivery_info,
            phone_number=order.phone_number,
            is_from_stock=order.is_from_stock,
            tracking_number=getattr(order, "tracking_number", None),
            tryon_discount_rub=float(getattr(order, "tryon_discount_rub", 0) or 0),
            reviewable_item_ids=reviewable_ids,
        ))
    
    return order_responses


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Получить заказ по ID"""
    result = await session.execute(
        select(Order)
        .options(joinedload(Order.delivery).joinedload(OrderDelivery.delivery_status))
        .where(
            Order.id == order_id,
            Order.user_id == user_id
        )
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    delivery_info = None
    if order.delivery:
        delivery_info = DeliveryInfo(
            status_name=order.delivery.delivery_status.name if order.delivery.delivery_status else None,
            additional_info=order.delivery.additional_info,
            updated_at=order.delivery.updated_at
        )
    enriched_data = await _enrich_order_data_with_photos(session, order.order_data)
    reviewable_ids = await _get_reviewable_item_ids(session, order, user_id) if order.status == "завершен" else None
    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        order_data=enriched_data,
        status=order.status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        paid_amount=float(order.paid_amount),
        order_total=compute_order_amount_due(
            order.order_data,
            float(getattr(order, "tryon_discount_rub", 0) or 0),
            float(((order.order_data or {}).get("delivery_snapshot") or {}).get("delivery_cost_rub") or 0),
            exclude_returned=True,
        ),
        delivery=delivery_info,
        phone_number=order.phone_number,
        is_from_stock=order.is_from_stock,
        tracking_number=getattr(order, "tracking_number", None),
        tryon_discount_rub=float(getattr(order, "tryon_discount_rub", 0) or 0),
        reviewable_item_ids=reviewable_ids,
    )


@router.post("/orders/{order_id}/hide")
async def hide_order_from_user(
    order_id: int,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Скрыть заказ из списка пользователя (мягкое удаление). Доступно только для статусов «отменен» и «завершен»."""
    result = await session.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order.status not in ("отменен", "завершен"):
        raise HTTPException(status_code=400, detail="Скрыть можно только отменённый или завершённый заказ")
    order.hidden_from_user_at = datetime.now(timezone.utc)
    await session.commit()
    return {"ok": True}


@router.post("/orders/{order_id}/reviews")
async def create_order_review(
    order_id: int,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
    item_id: int = Form(...),
    rating: int = Form(...),
    comment: str = Form(""),
    files: List[UploadFile] = File(default=[]),
):
    """Оставить отзыв по товару из завершённого заказа. Только для заказов со статусом «завершен». Фото сохраняются с уникальными именами."""
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Оценка должна быть от 1 до 5")
    result = await session.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order.status != "завершен":
        raise HTTPException(status_code=400, detail="Отзыв можно оставить только по завершённому заказу")
    items = (order.order_data or {}).get("items") or []
    item_ids_in_order = {item.get("item_id") for item in items if item.get("item_id") is not None}
    if item_id not in item_ids_in_order:
        raise HTTPException(status_code=400, detail="Товар не входит в состав этого заказа")
    existing = await session.execute(
        select(ItemReview).where(ItemReview.item_id == item_id, ItemReview.user_id == user_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Вы уже оставили отзыв на этот товар")
    photo_files = [f for f in files if f and getattr(f, "filename", None)][:MAX_REVIEW_PHOTOS]
    saved_paths = []
    for f in photo_files:
        content = await f.read()
        if not content:
            continue
        if len(content) > MAX_REVIEW_PHOTO_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Размер файла превышает {MAX_REVIEW_PHOTO_SIZE_BYTES // (1024 * 1024)} МБ",
            )
        content_type = (getattr(f, "content_type") or "").split(";")[0].strip().lower()
        if content_type and content_type not in ALLOWED_REVIEW_PHOTO_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Допустимые форматы фото: JPEG, PNG, WebP",
            )
        ext = (Path(f.filename or "").suffix or ".jpg").lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = UPLOAD_DIR_REVIEWS / unique_name
        async with aiofiles.open(file_path, "wb") as out:
            await out.write(content)
        relative = f"uploads/reviews/{unique_name}"
        saved_paths.append(relative)
    review = ItemReview(
        item_id=item_id,
        user_id=user_id,
        rating=rating,
        comment=(comment or "").strip() or None,
    )
    session.add(review)
    await session.flush()
    for idx, rel in enumerate(saved_paths):
        session.add(ItemReviewPhoto(review_id=review.id, file_path=rel, sort_order=idx))
    await session.commit()
    await session.refresh(review)

    return {"id": review.id, "item_id": review.item_id, "rating": review.rating}


@router.post("/orders/{order_id}/cancel")
async def cancel_order_by_user(
    order_id: int,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Отменить заказ (только для статусов «Ожидает» и «Выкуп»)."""
    result = await session.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order.status not in ("Ожидает", "Выкуп"):
        raise HTTPException(status_code=400, detail="Отменить можно только заказ со статусом «Ожидает» или «Выкуп»")
    if order.is_from_stock:
        await _release_reservations_for_order(order_id, session)
    if order.user_id:
        await release_tryon_for_order(order_id, order.user_id)
    await delete_promo_redemptions_for_order(session, order_id)
    order.status = "отменен"
    order.cancel_reason = "Отменён пользователем"
    await session.commit()
    await session.refresh(order)
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{FINANCE_SERVICE_URL}/internal/payments/cancel-order-payments",
                json={"order_id": order.id},
                headers={"X-Internal-Token": INTERNAL_TOKEN},
                timeout=30.0,
            )
    except Exception as e:
        logger.warning("Ошибка при отмене платежей заказа %s: %s", order_id, e)
    return {"id": order.id, "status": order.status}


@router.post("/orders/{order_id}/create-payment")
async def create_payment_for_order(
    order_id: int,
    request: CreatePaymentForOrderRequest,
    http_request: Request,
    user_id: int = Depends(get_user_id_for_request),
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session)
):
    """Создать платёж по заказу (прокси в finance). Сумма: товары − скидка за примерки + доставка."""
    order_result = await session.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    order_data: Dict[str, Any] = order.order_data or {}
    tryon_d = float(getattr(order, "tryon_discount_rub", 0) or 0)
    snapshot = (order_data or {}).get("delivery_snapshot") or {}
    delivery_cost = snapshot.get("delivery_cost_rub")
    if delivery_cost is None:
        delivery_cost = 0.0
    else:
        delivery_cost = float(delivery_cost)

    # Товары: те же line totals, что и compute_order_total (price уже с промо; скидка за примерки — отдельно)
    line_totals, goods_subtotal = line_totals_for_order_items(order_data, exclude_returned=True)
    order_total_check = float(compute_order_total(order_data, exclude_returned=True) or 0)
    if abs(goods_subtotal - order_total_check) > 0.02:
        logger.warning(
            "create_payment order_id=%s: goods_subtotal %s vs compute_order_total %s",
            order_id,
            goods_subtotal,
            order_total_check,
        )

    receipt_items: List[Dict[str, Any]] = []
    # ЮKassa payment_mode: заказ под заказ — full_prepayment (100% предоплата), из наличия — full_payment.
    receipt_primary_payment_mode = "full_prepayment" if not order.is_from_stock else "full_payment"
    line_meta: List[tuple] = []
    items_nr = [i for i in (order_data.get("items") or []) if not i.get("returned")]
    for item in items_nr:
        name = str(item.get("name") or "Товар")
        size = (item.get("size") or "").strip()
        if size:
            name = f"{name} (размер: {size})"
        qty = int(item.get("quantity", 1) or 1)
        line_meta.append((name, qty))

    if len(line_meta) != len(line_totals):
        raise HTTPException(
            status_code=500,
            detail="Несогласованность состава заказа при формировании платежа",
        )

    # Скидка за AI-примерки: отдельная строка «услуга» + full_payment; суммы товаров масштабируем так,
    # чтобы sum(товары) + услуга(tryon_d) = товары после одной скидки tryon_d (см. docs/RECEIPT_STRUCTURE.md).
    if tryon_d > 0 and 2 * tryon_d <= goods_subtotal + 1e-6:
        scale_discount = 2.0 * tryon_d
        append_tryon_service_line = True
    else:
        scale_discount = tryon_d
        append_tryon_service_line = False
    scaled_totals = scale_commodity_line_totals(line_totals, goods_subtotal, scale_discount)
    for (name, quantity), lt in zip(line_meta, scaled_totals):
        if lt <= 0:
            continue
        receipt_items.append({
            "description": name[:128],
            "quantity": str(quantity),
            "amount": {"value": f"{lt:.2f}", "currency": "RUB"},
            "vat_code": 1,  # ЮKassa vat_code: 1 = без НДС (УСН)
            "payment_mode": receipt_primary_payment_mode,
            "payment_subject": "commodity",
        })

    if append_tryon_service_line and tryon_d > 0:
        receipt_items.append({
            "description": "Программа AI-примерки (скидка с заказа)"[:128],
            "quantity": "1",
            "amount": {"value": f"{tryon_d:.2f}", "currency": "RUB"},
            "vat_code": 1,
            "payment_mode": "full_payment",
            "payment_subject": "service",
        })

    if delivery_cost and delivery_cost > 0:
        delivery_description = _build_delivery_description_for_receipt(snapshot.get("delivery_method_code"))
        receipt_items.append({
            "description": delivery_description[:128],
            "quantity": "1",
            "amount": {"value": f"{float(delivery_cost):.2f}", "currency": "RUB"},
            "vat_code": 1,  # ЮKassa vat_code: 1 = без НДС (УСН)
            "payment_mode": receipt_primary_payment_mode,
            "payment_subject": "commodity",
        })

    amount_value = compute_order_amount_due(
        order_data,
        tryon_d,
        delivery_cost,
        exclude_returned=True,
    )
    amount = Decimal(str(amount_value))
    # Пропуск ЮKassa: только владелец (admin_type owner в JWT); сотрудник с JWT не проходит сюда.
    jwt_admin_type = await get_jwt_admin_type_optional_from_request(http_request, authorization)
    if jwt_admin_type == "owner" and float(amount) > 0:
        await _apply_owner_waiver_order_payment(session, order, float(amount))
        await session.commit()
        await session.refresh(order)
        return {"confirmation_url": None, "owner_payment_skipped": True}

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть больше 0")

    if receipt_items:
        if not (order.phone_number or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Для оплаты с фискальным чеком в заказе нужен номер телефона. Укажите телефон при оформлении доставки.",
            )
        adjust_yookassa_receipt_sum_to_target(receipt_items, float(amount))
        receipt_sum = sum_yookassa_receipt_items_rub(receipt_items)
        if abs(receipt_sum - float(amount)) > 0.05:
            logger.error(
                "create_payment order_id=%s: сумма чека %.2f не совпадает с к оплате %.2f",
                order_id,
                receipt_sum,
                float(amount),
            )
            raise HTTPException(
                status_code=500,
                detail="Внутренняя ошибка: сумма позиций чека не совпадает с суммой платежа",
            )

    promo_snap = (order_data.get("promo_snapshot") or {}) if isinstance(order_data, dict) else {}
    promo_rub = promo_snap.get("discount_rub")
    meta_extra: Dict[str, str] = {
        "tryon_discount_rub": f"{tryon_d:.2f}",
        "goods_total_rub": f"{goods_subtotal:.2f}",
        "delivery_cost_rub": f"{float(delivery_cost):.2f}",
        "amount_due_rub": f"{int(amount):d}",
    }
    if promo_rub is not None:
        meta_extra["promo_discount_rub"] = f"{float(promo_rub):.2f}"

    try:
        async with httpx.AsyncClient() as client:
            payload: Dict[str, Any] = {
                "order_id": order_id,
                "user_id": user_id,
                "amount": str(amount),
                "return_url": request.return_url,
                "description": f"Оплата заказа #{order_id} (скидка AI-примерки: {tryon_d:.2f} ₽)",
                "metadata": meta_extra,
            }
            if receipt_items:
                payload["receipt_items"] = receipt_items
                payload["customer_phone"] = (order.phone_number or "").strip()
            resp = await client.post(
                f"{FINANCE_SERVICE_URL}/payments/create",
                json=payload,
                headers={"X-Internal-Token": INTERNAL_TOKEN},
                timeout=30.0,
            )
        if resp.status_code != 200:
            err = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            detail = err.get("detail", resp.text)
            raise HTTPException(status_code=resp.status_code, detail=detail)
        data = resp.json()
        confirmation_url = data.get("confirmation_url") if isinstance(data, dict) else getattr(data, "confirmation_url", None)
        return {"confirmation_url": confirmation_url}
    except httpx.RequestError as e:
        logger.exception("Ошибка вызова finance при создании платежа: %s", e)
        raise HTTPException(status_code=502, detail="Сервис оплаты недоступен")


@router.get("/internal/orders/all")
async def get_all_orders_for_finance(
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")
):
    """Получить все заказы для finance-service (внутренний endpoint)"""
    # Проверка внутреннего токена
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    # Получаем все заказы
    result = await session.execute(select(Order).order_by(Order.created_at.desc()))
    orders = result.scalars().all()
    
    # Преобразуем в список словарей с нужными полями для finance-service
    orders_list = []
    for order in orders:
        od = order.order_data or {}
        orders_list.append({
            "id": order.id,
            "status": order.status,
            "paid_amount": float(order.paid_amount),
            "estimated_cost": compute_order_amount_due(
                order.order_data,
                float(getattr(order, "tryon_discount_rub", 0) or 0),
                float(((order.order_data or {}).get("delivery_snapshot") or {}).get("delivery_cost_rub") or 0),
                exclude_returned=False,
            ),
            "refund_on_cancel": order.refund_on_cancel,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "is_from_stock": order.is_from_stock,
            "delivery_carrier_settlement": od.get("delivery_carrier_settlement"),
        })
    
    return orders_list


@router.post("/internal/orders/cleanup")
async def cleanup_old_orders(
    older_than_days: int = 180,
    status_to_clean: str = "отменен",
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
):
    """
    Очистка старых заказов по статусу (по умолчанию — отменённые старше 180 дней).
    Удаляются заказы и связанные order_delivery (по каскаду). Внутренний эндпоинт.
    """
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    if older_than_days < 1:
        raise HTTPException(status_code=400, detail="older_than_days должен быть не меньше 1")
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    result = await session.execute(
        select(Order).where(
            Order.status == status_to_clean,
            Order.created_at < cutoff,
        )
    )
    orders = result.scalars().all()
    deleted = 0
    for order in orders:
        await session.delete(order)
        deleted += 1
    if deleted:
        await session.commit()
    logger.info("Очистка заказов: удалено %s заказов со статусом %s старше %s дней", deleted, status_to_clean, older_than_days)
    return {"deleted": deleted, "status": status_to_clean, "older_than_days": older_than_days}


@router.get("/internal/orders/{order_id}")
async def get_order_by_id_internal(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")
):
    """Получить заказ по ID (внутренний endpoint для finance-service)"""
    # Проверка внутреннего токена
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    return {
        "id": order.id,
        "user_id": order.user_id,
        "status": order.status,
        "paid_amount": float(order.paid_amount),
        "estimated_cost": compute_order_amount_due(
            order.order_data,
            float(getattr(order, "tryon_discount_rub", 0) or 0),
            float(((order.order_data or {}).get("delivery_snapshot") or {}).get("delivery_cost_rub") or 0),
            exclude_returned=False,
        ),
        "order_data": order.order_data,
        "phone_number": order.phone_number,
        "is_from_stock": order.is_from_stock,
        "tracking_number": getattr(order, "tracking_number", None)
    }


@router.patch("/internal/orders/{order_id}/paid-amount")
async def update_order_paid_amount_internal(
    order_id: int,
    request: Dict[str, Any],
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")
):
    """Обновить внесенные средства заказа (внутренний endpoint для finance-service)"""
    # Проверка внутреннего токена
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    paid_amount = request.get("paid_amount")
    if paid_amount is None:
        raise HTTPException(status_code=400, detail="Не указан paid_amount")
    try:
        paid_amount = float(paid_amount)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="paid_amount должен быть числом")
    if paid_amount < 0:
        raise HTTPException(status_code=400, detail="Внесенные средства не могут быть отрицательными")
    if paid_amount > 1e9:
        raise HTTPException(status_code=400, detail="Недопустимое значение paid_amount")
    
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    from decimal import Decimal as DecimalType
    order.paid_amount = DecimalType(str(paid_amount))
    await session.commit()
    await session.refresh(order)
    
    logger.info(f"Обновлен paid_amount для заказа {order_id}: {paid_amount:.2f} ₽")
    
    return {
        "id": order.id,
        "paid_amount": float(order.paid_amount),
        "status": order.status
    }


@router.post("/internal/orders/{order_id}/status")
async def update_order_status_internal(
    order_id: int,
    request: Dict[str, Any],
    session: AsyncSession = Depends(get_session),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")
):
    """
    Обновить статус заказа (внутренний endpoint для finance-service).

    Доп. поля тела: cancel_reason (при new_status=отменен), restore_cart_items (bool) —
    вернуть позиции из order_data.items в корзину user_id после снятия резерва (наличие).
    """
    # Проверка внутреннего токена
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    new_status = request.get("new_status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Не указан new_status")
    if not isinstance(new_status, str):
        raise HTTPException(status_code=400, detail="new_status должен быть строкой")
    new_status = new_status.strip()
    
    valid_statuses = ["Ожидает", "Выкуп", "в работе", "Собран", "отменен", "завершен"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Неверный статус")
    
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    old_status = order.status
    
    # Если статус не меняется
    if old_status == new_status:
        return {
            "id": order.id,
            "status": order.status,
            "paid_amount": float(order.paid_amount)
        }
    
    # Обрабатываем остатки/резервы при изменении статуса
    # Отмена: снимаем резерв (резервы отменяются, ItemStock не менялся)
    if order.is_from_stock and new_status == "отменен":
        await _release_reservations_for_order(order_id, session)
        logger.info(f"Резервы сняты для отмененного заказа со склада {order_id}")
    if new_status == "отменен" and order.user_id and request.get("restore_cart_items"):
        await _restore_order_lines_to_user_cart(session, order.user_id, order)
        logger.info(
            "Состав заказа %s возвращён в корзину пользователя %s (restore_cart_items)",
            order_id,
            order.user_id,
        )
    # Собран/завершен: переводим резерв в списание (уменьшаем ItemStock, резервы → used)
    if order.is_from_stock and new_status in ("Собран", "завершен"):
        await _convert_reservations_to_deduction(order_id, session)
        logger.info(f"Резервы переведены в списание для заказа {order_id}")

    if new_status == "завершен" and order.user_id:
        try:
            await complete_tryon_for_order(order.id, order.user_id)
            order.tryon_discount_settled = True
        except Exception as e:
            logger.error("tryon complete для заказа %s: %s", order_id, e, exc_info=True)
            raise HTTPException(
                status_code=502,
                detail="Не удалось зафиксировать примерки в профиле пользователя. Повторите попытку.",
            )
    if new_status == "отменен" and order.user_id:
        await release_tryon_for_order(order.id, order.user_id)
    if new_status == "отменен":
        await delete_promo_redemptions_for_order(session, order_id)

    order.status = new_status

    # Если статус "отменен", устанавливаем причину отмены
    if new_status == "отменен":
        cancel_reason = request.get("cancel_reason", "Заказ не оплачен")
        order.cancel_reason = cancel_reason
    else:
        order.cancel_reason = None

    await session.commit()
    await session.refresh(order)
    
    logger.info(f"Статус заказа {order_id} изменен: {old_status} -> {new_status}")
    
    # Обработка перехода в статус "в работе" - подтверждаем платежи (capture) для заказов по предзаказу
    # Для заказов по предзаказу платежи подтверждаются при переходе в "в работе"
    # Для заказов из наличия платежи подтверждаются при переходе в "Собран"
    if new_status == "в работе" and old_status != "в работе" and not order.is_from_stock:
        logger.info(f"Заказ {order.id} (предзаказ) переходит в статус 'в работе': начинаем подтверждение платежей (capture)")
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"Вызываем capture-order-payments для заказа {order.id} через {FINANCE_SERVICE_URL}/internal/payments/capture-order-payments")
                capture_response = await client.post(
                    f"{FINANCE_SERVICE_URL}/internal/payments/capture-order-payments",
                    json={"order_id": order.id},
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    timeout=30.0
                )
                logger.info(f"Ответ от finance-service для заказа {order.id}: статус {capture_response.status_code}, тело: {capture_response.text}")
                if capture_response.status_code == 200:
                    result = capture_response.json()
                    logger.info(f"Платежи заказа {order.id} подтверждены: {result.get('captured_count', 0)} из {result.get('total_count', 0)}. Ошибки: {result.get('errors', [])}")
                else:
                    logger.warning(f"Ошибка при подтверждении платежей заказа {order.id}: {capture_response.status_code} - {capture_response.text}")
        except Exception as e:
            logger.error(f"Ошибка при подтверждении платежей заказа {order.id}: {e}", exc_info=True)
            # Не прерываем выполнение, но логируем ошибку
    
    # Обработка перехода в статус "Собран" - подтверждаем платежи (capture) для заказов из наличия
    # Для заказов из наличия платежи подтверждаются при переходе в "Собран"
    if new_status == "Собран" and old_status != "Собран" and order.is_from_stock:
        logger.info(f"Заказ {order.id} переходит в статус 'Собран': начинаем подтверждение платежей (capture)")
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"Вызываем capture-order-payments для заказа {order.id} через {FINANCE_SERVICE_URL}/internal/payments/capture-order-payments")
                capture_response = await client.post(
                    f"{FINANCE_SERVICE_URL}/internal/payments/capture-order-payments",
                    json={"order_id": order.id},
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    timeout=30.0
                )
                logger.info(f"Ответ от finance-service для заказа {order.id}: статус {capture_response.status_code}, тело: {capture_response.text}")
                if capture_response.status_code == 200:
                    result = capture_response.json()
                    logger.info(f"Платежи заказа {order.id} подтверждены: {result.get('captured_count', 0)} из {result.get('total_count', 0)}. Ошибки: {result.get('errors', [])}")
                else:
                    logger.warning(f"Ошибка при подтверждении платежей заказа {order.id}: {capture_response.status_code} - {capture_response.text}")
        except Exception as e:
            logger.error(f"Ошибка при подтверждении платежей заказа {order.id}: {e}", exc_info=True)
            # Не прерываем выполнение, но логируем ошибку
    
    # Обработка перехода в "отменен" - отменяем платежи в холде (cancel)
    if new_status == "отменен":
        try:
            async with httpx.AsyncClient() as client:
                cancel_response = await client.post(
                    f"{FINANCE_SERVICE_URL}/internal/payments/cancel-order-payments",
                    json={"order_id": order.id},
                    headers={"X-Internal-Token": INTERNAL_TOKEN},
                    timeout=30.0
                )
                if cancel_response.status_code == 200:
                    result = cancel_response.json()
                    logger.info(f"Платежи заказа {order.id} отменены: {result.get('canceled_count', 0)} из {result.get('total_count', 0)}")
                else:
                    logger.warning(f"Ошибка при отмене платежей заказа {order.id}: {cancel_response.status_code} - {cancel_response.text}")
        except Exception as e:
            logger.error(f"Ошибка при отмене платежей заказа {order.id}: {e}", exc_info=True)
            # Не прерываем выполнение, но логируем ошибку
    
    return {
        "id": order.id,
        "status": order.status,
        "paid_amount": float(order.paid_amount)
    }


class AttachOrderRequest(BaseModel):
    """Запрос на привязку заказа к пользователю"""
    user_id: int


@router.post("/internal/orders/{order_id}/attach")
async def attach_order_to_user(
    order_id: int,
    request: AttachOrderRequest,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session)
):
    """Привязать заказ к пользователю (внутренний endpoint)"""
    if not x_internal_token or not check_internal_token(x_internal_token):
        raise HTTPException(status_code=401, detail="Invalid internal token")
    
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    # Проверяем, не привязан ли заказ уже к другому пользователю
    if order.user_id is not None and order.user_id != request.user_id:
        raise HTTPException(status_code=400, detail="Заказ уже привязан к другому пользователю")
    
    if order.user_id is None:
        order.user_id = request.user_id
        await session.commit()
        await session.refresh(order)
    
    return {
        "id": order.id,
        "user_id": order.user_id,
        "status": order.status
    }

