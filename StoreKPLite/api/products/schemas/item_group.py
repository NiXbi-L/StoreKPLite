"""
Pydantic схемы для групп товаров
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ItemGroupResponse(BaseModel):
    """Ответ с информацией о группе"""
    id: int
    name: str
    created_at: datetime
    items_count: Optional[int] = None  # Количество товаров в группе


class ItemGroupWithItemsResponse(BaseModel):
    """Ответ с группой и товарами в ней"""
    id: int
    name: str
    created_at: datetime
    items: List[dict]  # Список товаров в группе


class CreateItemGroupRequest(BaseModel):
    """Запрос на создание группы"""
    name: str


class UpdateItemGroupRequest(BaseModel):
    """Запрос на обновление группы"""
    name: Optional[str] = None


class AddItemsToGroupRequest(BaseModel):
    """Запрос на добавление товаров в группу"""
    item_ids: List[int]


class RemoveItemFromGroupRequest(BaseModel):
    """Запрос на удаление товара из группы"""
    item_id: int



