"""
Роутер для авторизации ботов и мини-приложения (Telegram WebApp)
"""
import json
import secrets
from urllib.parse import parse_qsl
from os import getenv
from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi import status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta

from api.users.database.database import get_session
from api.users.models.user import User
from api.users.utils.avatar_display import effective_avatar_url
from api.users.models.admin import Admin
from api.users.utils.auth_tokens import (
    generate_internal_token,
    verify_internal_token,
    get_user_id_by_platform,
    cache_user_id_for_platform,
)
from api.users.utils.telegram_webapp import verify_telegram_webapp_data
from api.users.services.runtime_settings import is_miniapp_admin_only
from api.shared.auth import create_access_token, MINIAPP_ADMIN_ONLY_DETAIL

router = APIRouter()

# Только Telegram
PLATFORM = "telegram"


def _normalize_static_secret(raw: str | None) -> str:
    if not raw:
        return ""
    t = raw.strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t


def verify_bot_service_token(
    x_service_token: str | None = Header(None, alias="X-Service-Token"),
) -> None:
    """Тот же секрет, что INTERNAL_TOKEN у микросервисов: только бэкенд бота может выдать Redis-токен пользователя."""
    expected = getenv("INTERNAL_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTERNAL_TOKEN не настроен",
        )
    got = _normalize_static_secret(x_service_token)
    if len(got) != len(expected) or not secrets.compare_digest(got, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный сервисный токен",
        )


class AuthRequest(BaseModel):
    platform: str  # "telegram"
    platform_id: int  # Telegram User ID
    create_if_not_exists: bool = True
    first_name: str | None = None  # из Telegram, для обновления при логине бота
    username: str | None = None  # из Telegram (@username)


class AuthResponse(BaseModel):
    user_id: int
    token: str
    is_new_user: bool


class MiniappAuthRequest(BaseModel):
    initData: str


def _user_payload_for_jwt(user: User) -> dict:
    """Данные пользователя для JWT (без массивов). Только непустые поля."""
    payload = {"sub": str(user.id)}
    if user.tgid is not None:
        payload["tgid"] = user.tgid
    if user.firstname:
        payload["firstname"] = user.firstname
    if user.username:
        payload["username"] = user.username
    if user.country_code:
        payload["country_code"] = user.country_code
    if user.phone_local:
        payload["phone_local"] = user.phone_local
    if user.email:
        payload["email"] = user.email
    if user.gender:
        payload["gender"] = user.gender
    eff = effective_avatar_url(user)
    if eff:
        payload["avatar_url"] = eff
    payload["privacy_policy_accepted"] = user.privacy_policy_accepted
    return payload


def _apply_telegram_profile(user: User, first_name: str | None, username: str | None) -> bool:
    """Обновить firstname/username из Telegram при логине. Обновляем только если значение передано и отличается. Возвращает True если были изменения."""
    changed = False
    if first_name is not None:
        new_firstname = (first_name or "").strip() or None
        if user.firstname != new_firstname:
            user.firstname = new_firstname
            changed = True
    if username is not None:
        new_username = (username or "").strip() or None
        if user.username != new_username:
            user.username = new_username
            changed = True
    return changed


@router.post("/auth/miniapp")
async def auth_miniapp(
    request: MiniappAuthRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Авторизация в мини-приложении через подпись Telegram WebApp.
    Принимает initData из window.Telegram.WebApp.initData, проверяет подпись ботом,
    создаёт/находит пользователя и возвращает JWT с данными пользователя.
    """
    bot_token = getenv("BOT_TOKEN") or getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис авторизации не настроен (BOT_TOKEN)",
        )
    if not verify_telegram_webapp_data(request.initData, bot_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram authentication data",
        )
    parsed = dict(parse_qsl(request.initData))
    user_data_str = parsed.get("user")
    if not user_data_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No user data in initData",
        )
    try:
        user_json = json.loads(user_data_str)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user data in initData",
        )
    telegram_id = user_json.get("id")
    if not telegram_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No telegram id in user data",
        )
    result = await session.execute(select(User).where(User.tgid == telegram_id))
    user = result.scalar_one_or_none()
    is_new_user = False
    if not user:
        user = User(tgid=telegram_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        is_new_user = True

    # При каждом логине обновляем firstname и username из Telegram, если изменились
    tg_first_name = user_json.get("first_name")
    tg_username = user_json.get("username")
    changed = _apply_telegram_profile(user, tg_first_name, tg_username)

    photo_url = user_json.get("photo_url")
    if photo_url:
        url = photo_url.strip()
        norm = ("https://" + url[7:]) if url.lower().startswith("http://") else url
        if user.telegram_photo_url != norm:
            user.telegram_photo_url = norm
            changed = True

    if changed:
        await session.commit()
        await session.refresh(user)
    # Роль из таблицы admins — чтобы миниапп JWT совпадал с проверками (try-on и т.д.)
    admin_result = await session.execute(select(Admin).where(Admin.user_id == user.id))
    admin = admin_result.scalar_one_or_none()
    if await is_miniapp_admin_only(session) and admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MINIAPP_ADMIN_ONLY_DETAIL,
        )
    payload = _user_payload_for_jwt(user)
    # Любая строка в admins = доступ в миниапп при admin-only; claim обязателен (иначе JWT режут как у гостя).
    if admin:
        at = (admin.admin_type or "").strip()
        payload["admin_type"] = at if at else "staff"
    expire_minutes = int(getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 дней
    token = create_access_token(
        data=payload,
        expires_delta=timedelta(minutes=expire_minutes),
    )
    await cache_user_id_for_platform(user.id, PLATFORM, telegram_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "is_new_user": is_new_user,
    }


@router.post("/auth/bot", response_model=AuthResponse)
async def authenticate_bot(
    request: AuthRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_bot_service_token),
):
    """
    Авторизация бота — получение внутреннего user_id и внутреннего токена (Redis).
    Требуется заголовок X-Service-Token = INTERNAL_TOKEN (как у межсервисных вызовов).
    Поддерживается только платформа telegram.
    """
    if request.platform != PLATFORM:
        raise HTTPException(status_code=400, detail="Поддерживается только платформа telegram")
    result = await session.execute(select(User).where(User.tgid == request.platform_id))
    user = result.scalar_one_or_none()
    is_new_user = False
    if not user:
        if not request.create_if_not_exists:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        user = User(tgid=request.platform_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        is_new_user = True
    # Обновить firstname/username из Telegram, если бот передал и значения изменились
    if _apply_telegram_profile(user, request.first_name, request.username):
        await session.commit()
        await session.refresh(user)
    token = await generate_internal_token(
        user_id=user.id,
        platform=request.platform,
        platform_id=request.platform_id,
        ttl_seconds=86400,
    )
    return AuthResponse(user_id=user.id, token=token, is_new_user=is_new_user)


@router.get("/auth/check-user")
async def check_user_exists_endpoint(
    platform: str,
    platform_id: int,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_bot_service_token),
):
    """Проверить существование пользователя по platform_id (без создания и токена). Нужен X-Service-Token."""
    if platform != PLATFORM:
        raise HTTPException(status_code=400, detail="Поддерживается только платформа telegram")
    result = await session.execute(select(User).where(User.tgid == platform_id))
    user = result.scalar_one_or_none()
    return {"exists": user is not None}


@router.get("/auth/verify-internal")
async def verify_internal_token_endpoint(
    x_internal_token: str = Header(..., alias="X-Internal-Token"),
    x_platform_id: str = Header(..., alias="X-Platform-Id"),
    x_platform: str = Header(..., alias="X-Platform"),
):
    """Проверка внутреннего токена (для других микросервисов)."""
    user_id = await verify_internal_token(x_internal_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Невалидный токен")
    cached_user_id = await get_user_id_by_platform(x_platform, int(x_platform_id))
    if cached_user_id and cached_user_id != user_id:
        raise HTTPException(status_code=401, detail="Несоответствие токена и платформы")
    return {"user_id": user_id, "valid": True}
