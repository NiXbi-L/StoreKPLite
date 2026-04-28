"""Публичные эндпоинты режима миниаппа (без JWT)."""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.users.database.database import get_session
from api.users.services.runtime_settings import (
    default_guest_html,
    get_runtime_settings_row,
)

router = APIRouter()


@router.get("/public/miniapp-mode")
async def public_miniapp_mode(session: AsyncSession = Depends(get_session)):
    """Флаг «только админы» для миниаппа и межсервисной проверки JWT."""
    row = await get_runtime_settings_row(session)
    return {"admin_only": bool(row.miniapp_admin_only)}


@router.get("/public/miniapp-guest-html", response_class=HTMLResponse)
async def public_miniapp_guest_html(session: AsyncSession = Depends(get_session)):
    """HTML для пользователей, когда миниапп в режиме только для администраторов."""
    row = await get_runtime_settings_row(session)
    raw = (row.miniapp_guest_html or "").strip()
    body = raw if raw else default_guest_html()
    return HTMLResponse(content=body, status_code=200)
