"""
Внутренний endpoint для обновления номера телефона по Telegram ID.
Используется ботом при получении контакта (share contact) от пользователя.
"""
from os import getenv
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.users.database.database import get_session
from api.users.models.user import User
from sqlalchemy import select

router = APIRouter()

INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")


def _check_internal_token(token: Optional[str]) -> bool:
    if not token:
        return False
    clean = token.replace("Bearer ", "").strip() if token.startswith("Bearer") else token.strip()
    return clean == INTERNAL_TOKEN


class SetPhoneByTelegramRequest(BaseModel):
    telegram_id: int
    phone_number: str  # например "79001234567" или "+79001234567"


def _parse_phone(phone_number: str) -> tuple[str, str]:
    """Возвращает (country_code, phone_local). Пример: '+79001234567' -> ('+7', '9001234567')."""
    s = (phone_number or "").strip().replace(" ", "").replace("-", "")
    if not s:
        return ("", "")
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("8") and len(s) == 11:
        s = "7" + s[1:]
    if s.startswith("7") and len(s) == 11:
        return ("+7", s[1:])
    if s.startswith("7") and len(s) > 11:
        return ("+7", s[1:11])
    return ("", s[:20])


@router.post("/internal/set-phone-by-telegram")
async def set_phone_by_telegram(
    request: SetPhoneByTelegramRequest,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session),
):
    """
    Обновить номер телефона пользователя по Telegram ID.
    Вызывается ботом при получении контакта от пользователя (без кодов подтверждения).
    """
    if not x_internal_token or not _check_internal_token(x_internal_token):
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    if not request.phone_number or not request.phone_number.strip():
        raise HTTPException(status_code=400, detail="phone_number обязателен")

    country_code, phone_local = _parse_phone(request.phone_number)
    if not phone_local:
        raise HTTPException(status_code=400, detail="Некорректный номер телефона")

    result = await session.execute(
        select(User).where(User.tgid == request.telegram_id).with_for_update()
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    user.country_code = country_code or None
    user.phone_local = phone_local
    await session.commit()
    await session.refresh(user)
    return {"ok": True, "user_id": user.id}
