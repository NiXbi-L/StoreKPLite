"""
Роутер для работы с типами вещей
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from api.products.database.database import get_session
from api.products.models.item_type import ItemType
from api.products.models.item import Item
from api.products.schemas.item_type import (
    ItemTypeResponse,
    CreateItemTypeRequest,
    UpdateItemTypeRequest
)
from api.shared.jwt_admin_deps import require_jwt_permission

router = APIRouter()

check_admin_access = require_jwt_permission("catalog")


@router.get("/item-types", response_model=List[ItemTypeResponse])
async def list_item_types(
    session: AsyncSession = Depends(get_session)
):
    """Получить список типов вещей, у которых есть товары в каталоге (для фильтра без лишней нагрузки на БД)."""
    result = await session.execute(
        select(ItemType).where(ItemType.items_count > 0).order_by(ItemType.name)
    )
    item_types = result.scalars().all()
    return [ItemTypeResponse(
        id=item_type.id,
        name=item_type.name,
        created_at=item_type.created_at,
        items_count=getattr(item_type, "items_count", 0),
    ) for item_type in item_types]


@router.get("/admin/item-types", response_model=List[ItemTypeResponse])
async def list_item_types_admin(
    admin = Depends(check_admin_access),
    session: AsyncSession = Depends(get_session)
):
    """Получить список всех типов вещей (для админов), с полем items_count."""
    result = await session.execute(select(ItemType).order_by(ItemType.name))
    item_types = result.scalars().all()
    return [ItemTypeResponse(
        id=item_type.id,
        name=item_type.name,
        created_at=item_type.created_at,
        items_count=getattr(item_type, "items_count", 0),
    ) for item_type in item_types]


@router.get("/admin/item-types/{item_type_id}", response_model=ItemTypeResponse)
async def get_item_type(
    item_type_id: int,
    admin = Depends(check_admin_access),
    session: AsyncSession = Depends(get_session)
):
    """Получить тип вещи по ID (для админов)"""
    result = await session.execute(select(ItemType).where(ItemType.id == item_type_id))
    item_type = result.scalar_one_or_none()
    
    if not item_type:
        raise HTTPException(status_code=404, detail="Тип вещи не найден")
    
    return ItemTypeResponse(
        id=item_type.id,
        name=item_type.name,
        created_at=item_type.created_at,
        items_count=getattr(item_type, "items_count", 0),
    )


@router.post("/admin/item-types", response_model=ItemTypeResponse)
async def create_item_type(
    request: CreateItemTypeRequest,
    admin = Depends(check_admin_access),
    session: AsyncSession = Depends(get_session)
):
    """Создать новый тип вещи (для админов)"""
    # Проверяем, не существует ли уже тип с таким именем
    existing_result = await session.execute(
        select(ItemType).where(ItemType.name == request.name)
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Тип вещи с таким названием уже существует")
    
    item_type = ItemType(name=request.name, items_count=0)
    session.add(item_type)
    await session.commit()
    await session.refresh(item_type)
    return ItemTypeResponse(
        id=item_type.id,
        name=item_type.name,
        created_at=item_type.created_at,
        items_count=0,
    )


@router.put("/admin/item-types/{item_type_id}", response_model=ItemTypeResponse)
async def update_item_type(
    item_type_id: int,
    request: UpdateItemTypeRequest,
    admin = Depends(check_admin_access),
    session: AsyncSession = Depends(get_session)
):
    """Обновить тип вещи (для админов)"""
    result = await session.execute(select(ItemType).where(ItemType.id == item_type_id))
    item_type = result.scalar_one_or_none()
    
    if not item_type:
        raise HTTPException(status_code=404, detail="Тип вещи не найден")
    
    if request.name is not None:
        # Проверяем, не существует ли уже тип с таким именем (кроме текущего)
        existing_result = await session.execute(
            select(ItemType).where(
                ItemType.name == request.name,
                ItemType.id != item_type_id
            )
        )
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(status_code=400, detail="Тип вещи с таким названием уже существует")
        
        item_type.name = request.name
    
    await session.commit()
    await session.refresh(item_type)
    return ItemTypeResponse(
        id=item_type.id,
        name=item_type.name,
        created_at=item_type.created_at,
        items_count=getattr(item_type, "items_count", 0),
    )


@router.delete("/admin/item-types/{item_type_id}")
async def delete_item_type(
    item_type_id: int,
    admin = Depends(check_admin_access),
    session: AsyncSession = Depends(get_session)
):
    """Удалить тип вещи (для админов)"""
    result = await session.execute(select(ItemType).where(ItemType.id == item_type_id))
    item_type = result.scalar_one_or_none()
    
    if not item_type:
        raise HTTPException(status_code=404, detail="Тип вещи не найден")
    
    # Проверяем, используется ли этот тип вещи в товарах
    items_result = await session.execute(
        select(Item).where(Item.item_type_id == item_type_id)
    )
    items = items_result.scalars().all()
    
    if items:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя удалить тип вещи: он используется в {len(items)} товарах"
        )
    
    await session.delete(item_type)
    await session.commit()
    
    return {"message": "Тип вещи удален", "item_type_id": item_type_id}
