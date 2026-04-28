"""Внутренний поиск user_id по Telegram ID (для tryon и др.)."""

from os import getenv
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.users.database.database import get_session
from api.users.models.user import User

router = APIRouter()

_INTERNAL = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")


def _check_internal(x_internal_token: str | None) -> None:
    if x_internal_token != _INTERNAL:
        raise HTTPException(status_code=403, detail="Неверный внутренний токен")


@router.get("/internal/users/by-tgid/{tgid}")
async def internal_user_id_by_tgid(
    tgid: int,
    session: AsyncSession = Depends(get_session),
    x_internal_token: str | None = Header(None, alias="X-Internal-Token"),
):
    """Вернуть внутренний user_id по Telegram ID (только межсервисно)."""
    _check_internal(x_internal_token)
    if tgid <= 0:
        raise HTTPException(status_code=400, detail="Некорректный tgid")
    result = await session.execute(select(User.id).where(User.tgid == tgid))
    uid = result.scalar_one_or_none()
    if uid is None:
        raise HTTPException(status_code=404, detail="Пользователь с таким tgid не найден")
    return {"user_id": int(uid)}


class InternalUsersByIdsRequest(BaseModel):
    user_ids: Annotated[list[int], Field(min_length=0, max_length=1000)]


@router.post("/internal/users/by-ids")
async def internal_users_by_ids(
    body: InternalUsersByIdsRequest,
    session: AsyncSession = Depends(get_session),
    x_internal_token: str | None = Header(None, alias="X-Internal-Token"),
):
    """Пакетная выдача профилей по внутренним id (межсервисно, один ответ вместо N GET /users/{id})."""
    _check_internal(x_internal_token)
    raw = [int(x) for x in body.user_ids if int(x) > 0]
    ids = sorted(set(raw))
    if not ids:
        return {"users": []}
    # Ленивый импорт: иначе при загрузке роутера тянется users.py → jwt и пр.
    from api.users.routers.users import _user_response_from_orm

    result = await session.execute(select(User).where(User.id.in_(ids)))
    rows = result.scalars().all()
    return {"users": [_user_response_from_orm(u).model_dump() for u in rows]}
