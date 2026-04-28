"""
Обновление денормализованного счётчика items_count в item_types при CRUD товаров.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def change_item_type_count(session: AsyncSession, item_type_id: int, delta: int) -> None:
    """Увеличить или уменьшить items_count у типа. delta может быть отрицательным."""
    if not item_type_id:
        return
    await session.execute(
        text(
            "UPDATE item_types SET items_count = GREATEST(0, COALESCE(items_count, 0) + :delta) WHERE id = :id"
        ),
        {"id": item_type_id, "delta": delta},
    )
