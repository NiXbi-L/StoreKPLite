"""Настройки режима миниаппа (только владелец)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.users.database.database import get_session
from api.users.routers.admin import require_owner
from api.users.models.admin import Admin
from api.users.services.runtime_settings import default_guest_html, get_runtime_settings_row
from api.shared.auth import bump_miniapp_admin_only_cache

router = APIRouter()

MAX_GUEST_HTML = 500_000


class MiniappAccessStateResponse(BaseModel):
    miniapp_admin_only: bool
    guest_html: str


class MiniappAccessUpdateRequest(BaseModel):
    miniapp_admin_only: bool
    guest_html: str = Field(
        ...,
        description="Полный HTML документ для гостей; пустая строка — подставить шаблон по умолчанию",
        max_length=MAX_GUEST_HTML,
    )


@router.get("/admin/system/miniapp-access", response_model=MiniappAccessStateResponse)
async def get_miniapp_access_settings(
    _: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    row = await get_runtime_settings_row(session)
    html = (row.miniapp_guest_html or "").strip()
    if not html:
        html = default_guest_html()
    return MiniappAccessStateResponse(
        miniapp_admin_only=bool(row.miniapp_admin_only),
        guest_html=html,
    )


@router.put("/admin/system/miniapp-access", response_model=MiniappAccessStateResponse)
async def put_miniapp_access_settings(
    body: MiniappAccessUpdateRequest,
    _: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    row = await get_runtime_settings_row(session)
    row.miniapp_admin_only = body.miniapp_admin_only
    guest = body.guest_html.strip()
    row.miniapp_guest_html = None if not guest else body.guest_html
    await session.commit()
    await session.refresh(row)
    bump_miniapp_admin_only_cache()
    html = (row.miniapp_guest_html or "").strip()
    if not html:
        html = default_guest_html()
    return MiniappAccessStateResponse(
        miniapp_admin_only=bool(row.miniapp_admin_only),
        guest_html=html,
    )
