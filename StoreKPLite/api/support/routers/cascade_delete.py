"""
Роутер для каскадного удаления и проверки связей
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any, Optional
from os import getenv

from api.support.database.database import get_session
from api.support.models.support_ticket import SupportTicket

INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")

router = APIRouter()


def verify_internal_token(x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")):
    """Проверка внутреннего токена"""
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid internal token")
    return True


# Маппинг полей на модели
FIELD_TO_MODEL = {
    "user_id": {
        "SupportTicket": SupportTicket,
    }
}


@router.get("/internal/db/check-foreign-keys/{field_name}/{record_id}")
async def check_foreign_keys(
    field_name: str,
    record_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(verify_internal_token)
) -> Dict[str, Any]:
    """Проверить наличие связанных записей по foreign key"""
    
    if field_name not in FIELD_TO_MODEL:
        return {"has_relations": False, "relations": []}
    
    relations = []
    models = FIELD_TO_MODEL[field_name]
    
    for table_name, model_class in models.items():
        # Получаем количество связанных записей
        field = getattr(model_class, field_name)
        result = await session.execute(
            select(func.count(model_class.id)).where(field == record_id)
        )
        count = result.scalar() or 0
        
        if count > 0:
            relations.append({
                "service": "support",
                "table": table_name,
                "field": field_name,
                "count": count
            })
    
    return {
        "has_relations": len(relations) > 0,
        "relations": relations
    }


@router.delete("/internal/db/cascade-delete/{field_name}/{record_id}")
async def cascade_delete(
    field_name: str,
    record_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(verify_internal_token)
) -> Dict[str, Any]:
    """Каскадное удаление связанных записей"""
    
    if field_name not in FIELD_TO_MODEL:
        return {"deleted": 0, "tables": []}
    
    deleted_tables = []
    models = FIELD_TO_MODEL[field_name]
    
    for table_name, model_class in models.items():
        field = getattr(model_class, field_name)
        
        # Получаем записи для удаления
        result = await session.execute(
            select(model_class).where(field == record_id)
        )
        records = result.scalars().all()
        
        if records:
            count = len(records)
            for record in records:
                await session.delete(record)
            await session.commit()
            
            deleted_tables.append({
                "service": "support",
                "table": table_name,
                "deleted_count": count
            })
    
    return {
        "deleted": sum(t["deleted_count"] for t in deleted_tables),
        "tables": deleted_tables
    }


@router.delete("/internal/users/{user_id}/delete-all-data")
async def delete_all_user_data(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    _: bool = Depends(verify_internal_token),
) -> Dict[str, Any]:
    """Удалить все тикеты поддержки пользователя. Вызывается из users-service при удалении пользователя."""
    result = await session.execute(select(SupportTicket).where(SupportTicket.user_id == user_id))
    records = result.scalars().all()
    for rec in records:
        await session.delete(rec)
    if records:
        await session.commit()
    return {
        "service": "support",
        "user_id": user_id,
        "deleted": len(records),
        "tables": [{"table": "support_tickets", "deleted_count": len(records)}] if records else [],
    }

