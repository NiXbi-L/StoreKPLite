"""
Pydantic схемы для типов вещей
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ItemTypeResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    items_count: int = 0


class CreateItemTypeRequest(BaseModel):
    name: str


class UpdateItemTypeRequest(BaseModel):
    name: Optional[str] = None
