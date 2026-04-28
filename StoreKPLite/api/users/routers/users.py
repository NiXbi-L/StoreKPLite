"""
Роутер для работы с пользователями
"""
import logging
import os
from datetime import timedelta
from os import getenv

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from api.shared.auth import create_access_token, get_user_id_for_request
from api.users.database.database import get_session
from api.users.models.admin import Admin
from api.users.models.user import User
from api.users.routers.auth import _user_payload_for_jwt
from api.users.utils.avatar_display import effective_avatar_url
from api.users.utils.profile_avatar_storage import (
    save_profile_avatar_jpeg,
    try_remove_stored_profile_avatar,
)
logger = logging.getLogger(__name__)

router = APIRouter()


def _ensure_https(url: Optional[str]) -> Optional[str]:
    """Нормализация URL аватара в https для избежания mixed content на HTTPS-страницах."""
    if not url or not str(url).strip().lower().startswith("http://"):
        return url
    return "https://" + str(url).strip()[7:]


def _upload_root() -> str:
    return getenv("USERS_UPLOAD_DIR", os.path.join(os.getcwd(), "uploads"))


class UserResponse(BaseModel):
    id: int
    tgid: Optional[int] = None
    firstname: Optional[str] = None
    username: Optional[str] = None
    country_code: Optional[str] = None
    phone_local: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    avatar_url: Optional[str] = None
    telegram_photo_url: Optional[str] = None
    profile_avatar_url: Optional[str] = None
    privacy_policy_accepted: bool = False
    feed_onboarding_seen: bool = False
    created_at: str

    class Config:
        from_attributes = True


class UpdateUserRequest(BaseModel):
    gender: Optional[str] = None
    privacy_policy_accepted: Optional[bool] = None
    feed_onboarding_seen: Optional[bool] = None
    country_code: Optional[str] = None
    phone_local: Optional[str] = None
    email: Optional[str] = None


class UpdateUserResponse(UserResponse):
    """Ответ PATCH /users/me: данные профиля + новый JWT с актуальными данными."""
    access_token: str


def _user_response_from_orm(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        tgid=user.tgid,
        firstname=user.firstname,
        username=user.username,
        country_code=user.country_code,
        phone_local=user.phone_local,
        email=user.email,
        gender=user.gender,
        avatar_url=_ensure_https(effective_avatar_url(user)),
        telegram_photo_url=_ensure_https(user.telegram_photo_url),
        profile_avatar_url=_ensure_https(user.profile_avatar_url),
        privacy_policy_accepted=user.privacy_policy_accepted,
        feed_onboarding_seen=getattr(user, "feed_onboarding_seen", False),
        created_at=user.created_at.isoformat(),
    )


async def _build_update_user_response(session: AsyncSession, user: User) -> UpdateUserResponse:
    await session.refresh(user)
    expire_minutes = int(getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
    payload = _user_payload_for_jwt(user)
    admin_row = (
        await session.execute(select(Admin).where(Admin.user_id == user.id))
    ).scalar_one_or_none()
    if admin_row:
        at = (admin_row.admin_type or "").strip()
        payload["admin_type"] = at if at else "staff"
    new_token = create_access_token(
        data=payload,
        expires_delta=timedelta(minutes=expire_minutes),
    )
    base = _user_response_from_orm(user)
    return UpdateUserResponse(
        **base.model_dump(),
        access_token=new_token,
    )


@router.get("/users/me", response_model=UserResponse)
async def get_current_user(
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """Получить информацию о текущем пользователе"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return _user_response_from_orm(user)


@router.patch("/users/me", response_model=UpdateUserResponse)
async def update_current_user(
    request: UpdateUserRequest,
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """Обновить информацию о текущем пользователе. Возвращает новый JWT с актуальными данными — клиент должен сохранить его и использовать вместо старого."""
    from datetime import datetime

    result = await session.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if request.gender is not None:
        user.gender = (request.gender.strip() or None) if request.gender else None
    if request.privacy_policy_accepted is not None:
        user.privacy_policy_accepted = request.privacy_policy_accepted
        if request.privacy_policy_accepted:
            user.privacy_policy_accepted_at = datetime.now()
    if request.feed_onboarding_seen is not None:
        user.feed_onboarding_seen = request.feed_onboarding_seen
    if request.country_code is not None:
        user.country_code = request.country_code
    if request.phone_local is not None:
        user.phone_local = request.phone_local
    if request.email is not None:
        user.email = request.email
    await session.commit()
    return await _build_update_user_response(session, user)


@router.post("/users/me/profile-avatar", response_model=UpdateUserResponse)
async def upload_profile_avatar(
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
    file: UploadFile = File(...),
):
    """Загрузить аватар профиля (квадрат по центру, до 384px). Telegram-фото остаётся в telegram_photo_url как фолбек."""
    result = await session.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    ct = (file.content_type or "").lower().split(";")[0].strip()
    if ct not in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
        raise HTTPException(
            status_code=400,
            detail="Нужно изображение в формате JPEG, PNG или WebP",
        )
    raw = await file.read()
    upload_root = _upload_root()
    old_url = user.profile_avatar_url
    try:
        new_url = await save_profile_avatar_jpeg(upload_root, user.id, raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Файл слишком большой")
    except Exception:
        logger.exception("profile avatar: обработка изображения")
        raise HTTPException(status_code=400, detail="Не удалось обработать изображение")
    try_remove_stored_profile_avatar(upload_root, old_url)
    user.profile_avatar_url = new_url
    await session.commit()
    return await _build_update_user_response(session, user)


@router.delete("/users/me/profile-avatar", response_model=UpdateUserResponse)
async def delete_profile_avatar(
    user_id: int = Depends(get_user_id_for_request),
    session: AsyncSession = Depends(get_session),
):
    """Убрать загруженный аватар; снова будет использоваться фото из Telegram (если есть)."""
    result = await session.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    upload_root = _upload_root()
    if user.profile_avatar_url:
        try_remove_stored_profile_avatar(upload_root, user.profile_avatar_url)
        user.profile_avatar_url = None
        await session.commit()
    return await _build_update_user_response(session, user)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Получить информацию о пользователе по ID (для внутреннего использования)"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return _user_response_from_orm(user)
