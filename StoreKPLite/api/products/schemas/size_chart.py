"""
Схемы для размерных сеток.
"""
from typing import List, Any, Optional

from pydantic import BaseModel, field_validator


def _normalize_grid(v: Any) -> dict:
    """Привести grid к формату { rows: [[str, ...], ...] }."""
    if v is None:
        return {"rows": []}
    if isinstance(v, dict) and "rows" in v:
        rows = v["rows"]
        if not isinstance(rows, list):
            return {"rows": []}
        return {"rows": [[str(cell) for cell in row] if isinstance(row, list) else [] for row in rows]}
    return {"rows": []}


class SizeChartResponse(BaseModel):
    """Размерная сетка для ответа (в карточке товара и в админке)."""
    id: int
    name: str
    grid: dict  # {"rows": [["ячейка", ...], ...]}


class SizeChartListItem(BaseModel):
    """Элемент списка размерных сеток (id + название для выбора в админке)."""
    id: int
    name: str


class CreateSizeChartRequest(BaseModel):
    """Создание размерной сетки."""
    name: str
    grid: dict  # {"rows": [[str, ...], ...]}

    @field_validator("grid", mode="before")
    @classmethod
    def ensure_grid(cls, v: Any) -> dict:
        return _normalize_grid(v)


class UpdateSizeChartRequest(BaseModel):
    """Обновление размерной сетки."""
    name: Optional[str] = None
    grid: Optional[dict] = None

    @field_validator("grid", mode="before")
    @classmethod
    def ensure_grid(cls, v: Any) -> dict | None:
        if v is None:
            return None
        return _normalize_grid(v)
