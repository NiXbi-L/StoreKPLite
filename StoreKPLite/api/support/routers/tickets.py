"""
Роутер для тикетов поддержки
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from api.support.database.database import get_session
from api.support.models.support_ticket import SupportTicket
from api.shared.auth import get_user_id_for_request

router = APIRouter()


class CreateTicketRequest(BaseModel):
    text: str
    photos: Optional[List[str]] = None


class TicketResponse(BaseModel):
    id: int
    user_id: Optional[int]
    username: Optional[str]
    text: str
    photos: Optional[List[str]]
    status: str
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


@router.post("/tickets", response_model=TicketResponse)
async def create_ticket(
    request: CreateTicketRequest,
    username: Optional[str] = None,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Создать тикет поддержки"""
    # Преобразуем photos из списка строк путей в JSON
    photos_json = request.photos if request.photos else None
    
    new_ticket = SupportTicket(
        user_id=user_id,
        username=username,
        text=request.text,
        photos=photos_json,
        status="Ожидает"
    )
    
    session.add(new_ticket)
    await session.commit()
    await session.refresh(new_ticket)
    
    return TicketResponse(
        id=new_ticket.id,
        user_id=new_ticket.user_id,
        username=new_ticket.username,
        text=new_ticket.text,
        photos=new_ticket.photos,
        status=new_ticket.status,
        created_at=new_ticket.created_at.isoformat(),
        updated_at=new_ticket.updated_at.isoformat()
    )


@router.get("/tickets", response_model=List[TicketResponse])
async def get_user_tickets(
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Получить все тикеты пользователя"""
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.user_id == user_id)
        .order_by(SupportTicket.created_at.desc())
    )
    tickets = result.scalars().all()
    
    return [
        TicketResponse(
            id=ticket.id,
            user_id=ticket.user_id,
            username=ticket.username,
            text=ticket.text,
            photos=ticket.photos,
            status=ticket.status,
            created_at=ticket.created_at.isoformat(),
            updated_at=ticket.updated_at.isoformat()
        )
        for ticket in tickets
    ]


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: int,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session)
):
    """Получить тикет по ID"""
    result = await session.execute(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.user_id == user_id
        )
    )
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    
    return TicketResponse(
        id=ticket.id,
        user_id=ticket.user_id,
        username=ticket.username,
        text=ticket.text,
        photos=ticket.photos,
        status=ticket.status,
        created_at=ticket.created_at.isoformat(),
        updated_at=ticket.updated_at.isoformat()
    )

