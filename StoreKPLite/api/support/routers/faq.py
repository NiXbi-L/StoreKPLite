"""
Роутер для FAQ
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from pydantic import BaseModel

from api.support.database.database import get_session
from api.support.models.faq import FAQ

router = APIRouter()


class FAQResponse(BaseModel):
    id: int
    title: str
    body: str
    created_at: str
    
    class Config:
        from_attributes = True


@router.get("/faq", response_model=List[FAQResponse])
async def get_faq_list(
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    """Получить список FAQ"""
    result = await session.execute(
        select(FAQ).offset(skip).limit(limit).order_by(FAQ.id.desc())
    )
    faqs = result.scalars().all()
    
    return [
        FAQResponse(
            id=faq.id,
            title=faq.title,
            body=faq.body,
            created_at=faq.created_at.isoformat()
        )
        for faq in faqs
    ]


@router.get("/faq/{faq_id}", response_model=FAQResponse)
async def get_faq(
    faq_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Получить FAQ по ID"""
    result = await session.execute(select(FAQ).where(FAQ.id == faq_id))
    faq = result.scalar_one_or_none()
    
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ не найден")
    
    return FAQResponse(
        id=faq.id,
        title=faq.title,
        body=faq.body,
        created_at=faq.created_at.isoformat()
    )

