"""
Роутер для корзины
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import List, Optional

from api.products.database.database import get_session
from api.products.models.cart import Cart
from api.products.models.item import Item
from api.products.models.item_photo import ItemPhoto
from api.products.models.item_type import ItemType
from sqlalchemy.orm import joinedload
from sqlalchemy import and_
from api.products.schemas.item import ItemResponse, ItemPhotoResponse
from api.products.utils.parcel import build_line_items_for_parcel, aggregate_parcel_dimensions
from api.shared.auth import get_user_id_for_request
from typing import Dict, Any

router = APIRouter()


async def _get_available_stock(item_id: int, size: Optional[str], session: AsyncSession) -> int:
    """StoreKPLite: складской учёт отключён, товар считаем доступным."""
    _ = (item_id, size, session)
    return 10**9


class CartParcelRequest(BaseModel):
    cart_item_ids: List[int]


class CartParcelResponse(BaseModel):
    weight_gram: int
    length_cm: int
    width_cm: int
    height_cm: int


class CartItemResponse(BaseModel):
    id: int
    item: ItemResponse
    size: Optional[str] = None
    quantity: int
    stock_type: str  # StoreKPLite: всегда "in_stock"
    price_rub: Optional[float] = None  # Цена в рублях (фиксированная)


class AddToCartRequest(BaseModel):
    item_id: int
    size: Optional[str] = None
    quantity: int = 1
    stock_type: Optional[str] = None  # Игнорируется в StoreKPLite


@router.post("/cart/items")
async def add_to_cart(
    request: AddToCartRequest,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """StoreKPLite: добавление товара в корзину всегда как "in_stock"."""
    effective_stock_type = "in_stock"
    
    # Проверяем, существует ли товар
    result = await session.execute(select(Item).where(Item.id == request.item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")
    
    # Проверяем, есть ли уже этот товар с таким размером и типом в корзине
    existing_result = await session.execute(
        select(Cart).where(
            and_(
                Cart.user_id == user_id,
                Cart.item_id == request.item_id,
                Cart.size == request.size,
                Cart.stock_type == effective_stock_type
            )
        )
    )
    existing_cart_item = existing_result.scalar_one_or_none()

    if existing_cart_item:
        existing_cart_item.quantity += request.quantity
    else:
        new_cart_item = Cart(
            user_id=user_id,
            item_id=request.item_id,
            size=request.size,
            quantity=request.quantity,
            stock_type=effective_stock_type
        )
        session.add(new_cart_item)

    await session.commit()

    return {"success": True, "stock_type": effective_stock_type}


@router.get("/cart/items")
async def get_cart_items(
    user_id: int = Depends(get_user_id_for_request),
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Получить все товары из корзины с расчетом цен"""
    result = await session.execute(
        select(Cart).where(Cart.user_id == user_id)
    )
    cart_items = result.scalars().all()
    
    items_data = []
    for cart_item in cart_items:
        # Получаем товар
        item_result = await session.execute(
            select(Item).options(joinedload(Item.item_type_rel)).where(Item.id == cart_item.item_id)
        )
        item = item_result.unique().scalar_one_or_none()
        
        if item:
            # Получаем только первое фото (для превью в корзине)
            photos_result = await session.execute(
                select(ItemPhoto).where(ItemPhoto.item_id == item.id).order_by(ItemPhoto.id).limit(1)
            )
            first_photo = photos_result.scalars().first()
            
            # StoreKPLite: только фиксированная цена в рублях.
            fixed_price_rub = float(item.fixed_price) if getattr(item, "fixed_price", None) is not None else None
            price_rub = fixed_price_rub if fixed_price_rub is not None else float(item.price)
            sizes_stock = []
            
            # Создаем словарь с дополнительным полем price_rub для удобства
            item_dict = {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "price": float(item.price),
                "price_rub": price_rub,
                "fixed_price_rub": fixed_price_rub,
                "size": item.size,
                "photo": first_photo.file_path if first_photo else None,
                "sizes_stock": sizes_stock,
            }

            stock_type_out = "in_stock"

            items_data.append({
                "id": cart_item.id,
                "item": item_dict,
                "size": cart_item.size,
                "quantity": cart_item.quantity,
                "stock_type": stock_type_out,
                "price_rub": price_rub
            })

    return items_data


class SetCartQuantityByItemRequest(BaseModel):
    item_id: int
    size: Optional[str] = None
    quantity: int  # Абсолютное значение; 0 — удалить из корзины


@router.patch("/cart/items/by-item")
async def set_cart_quantity_by_item(
    body: SetCartQuantityByItemRequest,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """Установить количество товара в корзине по item_id и размеру (ввод с клавиатуры или итог после +/-)."""
    size_val = (body.size or "").strip() or None
    result = await session.execute(
        select(Cart).where(
            and_(
                Cart.user_id == user_id,
                Cart.item_id == body.item_id,
                (Cart.size == size_val if size_val is not None else Cart.size.is_(None)),
            )
        )
    )
    rows = result.scalars().all()
    if body.quantity <= 0:
        for row in rows:
            await session.delete(row)
        await session.commit()
        return {"success": True, "quantity": 0}
    if rows:
        first = rows[0]
        qty = body.quantity
        first.stock_type = "in_stock"
        first.quantity = qty
        for row in rows[1:]:
            await session.delete(row)
        await session.commit()
        return {"success": True, "quantity": qty}
    else:
        item_result = await session.execute(select(Item).where(Item.id == body.item_id))
        item = item_result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")
        stock_type = "in_stock"
        qty = body.quantity
        session.add(
            Cart(
                user_id=user_id,
                item_id=body.item_id,
                size=size_val,
                quantity=qty,
                stock_type=stock_type,
            )
        )
    await session.commit()
    return {"success": True, "quantity": qty}


class UpdateCartItemSizeRequest(BaseModel):
    size: Optional[str] = None


@router.patch("/cart/items/{cart_item_id}/size")
async def update_cart_item_size(
    cart_item_id: int,
    body: UpdateCartItemSizeRequest,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """
    Изменить размер позиции корзины.
    Если уже есть позиция с тем же item_id, новым размером и тем же stock_type —
    объединяем (складываем quantity и удаляем исходную).
    """
    size_val = (body.size or "").strip() or None

    result = await session.execute(
        select(Cart).where(
            and_(
                Cart.id == cart_item_id,
                Cart.user_id == user_id,
            )
        )
    )
    cart_item = result.scalar_one_or_none()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Товар в корзине не найден")

    # Если размер не изменился — ничего не делаем
    if (cart_item.size or None) == size_val:
        return {"success": True}

    cart_item.stock_type = "in_stock"

    # Ищем другую позицию, с которой можно объединить (тот же товар, размер и тип заказа)
    existing_result = await session.execute(
        select(Cart).where(
            and_(
                Cart.user_id == user_id,
                Cart.item_id == cart_item.item_id,
                (Cart.size == size_val if size_val is not None else Cart.size.is_(None)),
                Cart.stock_type == cart_item.stock_type,
                Cart.id != cart_item_id,
            )
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        # Объединяем: переносим количество и удаляем исходную запись.
        new_total = existing.quantity + cart_item.quantity
        existing.quantity = new_total
        await session.delete(cart_item)
    else:
        # Просто меняем размер.
        cart_item.size = size_val

    await session.commit()
    return {"success": True}


@router.put("/cart/items/{cart_item_id}")
async def update_cart_item(
    cart_item_id: int,
    quantity: int,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Обновить количество товара в корзине по id позиции."""
    result = await session.execute(
        select(Cart).where(
            and_(
                Cart.id == cart_item_id,
                Cart.user_id == user_id
            )
        )
    )
    cart_item = result.scalar_one_or_none()
    
    if not cart_item:
        raise HTTPException(status_code=404, detail="Товар в корзине не найден")

    if quantity <= 0:
        await session.delete(cart_item)
    else:
        cart_item.stock_type = "in_stock"
        cart_item.quantity = quantity

    await session.commit()

    return {"success": True}


@router.delete("/cart/items/{cart_item_id}")
async def remove_from_cart(
    cart_item_id: int,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Удалить товар из корзины"""
    result = await session.execute(
        select(Cart).where(
            Cart.id == cart_item_id,
            Cart.user_id == user_id
        )
    )
    cart_item = result.scalar_one_or_none()
    
    if cart_item:
        await session.delete(cart_item)
        await session.commit()
    
    return {"success": True}


@router.get("/cart/check-stock")
async def check_cart_stock_availability(
    order_type: Optional[str] = Query(None, description="Фильтр по типу товаров: 'in_stock' или 'preorder'"),
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Таблица item_stock удалена — проверка наличия отключена. Всегда возвращаем all_available=True."""
    return {
        "all_available": True,
        "unavailable_items": [],
        "message": "Все товары в наличии"
    }


@router.patch("/cart/items/{cart_item_id}/stock-type")
async def update_cart_item_stock_type(
    cart_item_id: int,
    stock_type: str,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """StoreKPLite: тип заказа отключен, все позиции считаются in_stock."""
    
    result = await session.execute(
        select(Cart).where(
            and_(
                Cart.id == cart_item_id,
                Cart.user_id == user_id
            )
        )
    )
    cart_item = result.scalar_one_or_none()
    
    if not cart_item:
        raise HTTPException(status_code=404, detail="Товар в корзине не найден")
    
    # Дедупликация по canonical stock_type=in_stock
    existing_result = await session.execute(
        select(Cart).where(
            and_(
                Cart.user_id == user_id,
                Cart.item_id == cart_item.item_id,
                Cart.size == cart_item.size,
                Cart.stock_type == "in_stock"
            )
        )
    )
    existing_item = existing_result.scalar_one_or_none()
    
    if existing_item and existing_item.id != cart_item_id:
        existing_item.quantity += cart_item.quantity
        await session.delete(cart_item)
    else:
        cart_item.stock_type = "in_stock"
    
    await session.commit()
    
    _ = stock_type
    return {"success": True, "stock_type": "in_stock"}


@router.delete("/cart/clear")
async def clear_cart(
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Очистить всю корзину"""
    result = await session.execute(
        select(Cart).where(Cart.user_id == user_id)
    )
    cart_items = result.scalars().all()
    
    for cart_item in cart_items:
        await session.delete(cart_item)
    
    await session.commit()
    
    return {"success": True}


@router.post("/cart/parcel", response_model=CartParcelResponse)
async def get_cart_parcel(
    body: CartParcelRequest,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """
    Габариты и вес сборной посылки по выбранным позициям корзины (для расчёта стоимости доставки).
    Принимает список cart_item_id; возвращает суммарные weight_gram, length_cm, width_cm, height_cm.
    """
    if not body.cart_item_ids:
        return CartParcelResponse(
            weight_gram=1000,
            length_cm=40,
            width_cm=30,
            height_cm=10,
        )
    result = await session.execute(
        select(Cart).where(
            and_(
                Cart.user_id == user_id,
                Cart.id.in_(body.cart_item_ids),
            )
        )
    )
    cart_items = result.scalars().all()
    if not cart_items:
        return CartParcelResponse(
            weight_gram=1000,
            length_cm=40,
            width_cm=30,
            height_cm=10,
        )
    item_ids = list({c.item_id for c in cart_items})
    items_result = await session.execute(
        select(Item).where(Item.id.in_(item_ids))
    )
    items_list = items_result.scalars().all()
    items_by_id = {item.id: item for item in items_list}
    order_data_items = [
        {"item_id": c.item_id, "quantity": c.quantity}
        for c in cart_items
    ]
    line_items = build_line_items_for_parcel(order_data_items, items_by_id)
    parcel = aggregate_parcel_dimensions(line_items)
    return CartParcelResponse(
        weight_gram=parcel["weight_gram"],
        length_cm=parcel["length_cm"],
        width_cm=parcel["width_cm"],
        height_cm=parcel["height_cm"],
    )

