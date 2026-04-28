"""
Инвалидация JWT админки на всех устройствах: счётчик в Redis на user_id (admin — тот же user_id).

Токены, выданные POST /users/admin/login, содержат claim "arv" и поле "login".
Миниапп JWT без "login" не проверяется здесь.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from os import getenv
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Состояние админских JWT (arv, sid active/revoked) должно быть общим для всех сервисов.
# Если у сервиса свой REDIS_URL (кеш каталога и т.д.), задайте ADMIN_JWT_REDIS_URL на Redis users-service.
REDIS_URL = (getenv("ADMIN_JWT_REDIS_URL") or getenv("REDIS_URL") or "").strip()

_client: Optional[redis.Redis] = None


def _key(user_id: int) -> str:
    return f"timoshka:admin_jwt_gen:{user_id}"


def _sid_revoked_key(sid: str) -> str:
    return f"timoshka:admin_jwt_revoked_sid:{sid}"


def _sid_active_key(sid: str) -> str:
    return f"timoshka:admin_jwt_active_sid:{sid}"


async def _redis() -> Optional[redis.Redis]:
    global _client
    if not REDIS_URL:
        return None
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


async def get_admin_jwt_rev_for_login(user_id: int) -> int:
    """Текущее поколение сессии для встраивания в новый JWT при входе в админку."""
    r = await _redis()
    if r is None:
        return 0
    raw = await r.get(_key(user_id))
    return int(raw) if raw is not None else 0


async def bump_admin_jwt_rev(user_id: int) -> None:
    """Сбросить все выданные через /admin/login токены для этого пользователя."""
    r = await _redis()
    if r is None:
        logger.warning("REDIS_URL не задан — bump_admin_jwt_rev пропущен для user_id=%s", user_id)
        return
    await r.incr(_key(user_id))


async def bump_admin_jwt_rev_many(user_ids: list[int]) -> None:
    for uid in user_ids:
        if uid is not None:
            await bump_admin_jwt_rev(int(uid))


def is_admin_portal_jwt_payload(payload: dict) -> bool:
    """Только токен из admin/login (есть login); миниапп такие поля не кладёт."""
    login = payload.get("login")
    if not login or not str(login).strip():
        return False
    return True


async def ensure_admin_portal_jwt_still_valid(payload: dict) -> None:
    from fastapi import HTTPException, status

    if not is_admin_portal_jwt_payload(payload):
        return
    uid_raw = payload.get("sub")
    if uid_raw is None:
        return
    try:
        user_id = int(uid_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    r = await _redis()
    if r is None:
        return

    raw = await r.get(_key(user_id))
    current = int(raw) if raw is not None else 0
    token_arv = payload.get("arv")

    if token_arv is None:
        if current == 0:
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется повторный вход",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        t = int(token_arv)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if t != current:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия сброшена. Войдите снова.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def activate_admin_sid(sid: str, ttl_days: int = 120) -> None:
    """Пометить sid активным в Redis (TTL чуть больше жизни refresh)."""
    s = (sid or "").strip()
    if not s:
        return
    r = await _redis()
    if r is None:
        return
    await r.set(_sid_active_key(s), "1", ex=timedelta(days=max(1, int(ttl_days))))


async def deactivate_admin_sid(sid: str) -> None:
    """Сброс сессии: удалить sid из активных (быстрый revoke через DEL)."""
    s = (sid or "").strip()
    if not s:
        return
    r = await _redis()
    if r is None:
        return
    await r.delete(_sid_active_key(s))


async def revoke_admin_sid(sid: str, ttl_days: int = 120) -> None:
    """Отметить sid отозванным в Redis (достаточно для проверки в любом сервисе)."""
    s = (sid or "").strip()
    if not s:
        return
    r = await _redis()
    if r is None:
        return
    await r.set(_sid_revoked_key(s), "1", ex=timedelta(days=ttl_days))


async def ensure_admin_sid_not_revoked(payload: dict) -> None:
    """Проверка, что sid токена не был отозван через devices/logout."""
    if not is_admin_portal_jwt_payload(payload):
        return
    sid = str(payload.get("sid") or "").strip()
    if not sid:
        return
    r = await _redis()
    if r is None:
        return
    if await r.exists(_sid_revoked_key(sid)):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия завершена. Войдите снова.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def ensure_admin_sid_is_active(payload: dict) -> None:
    """Проверка активной сессии по sid (DEL = мгновенный logout/revoke)."""
    if not is_admin_portal_jwt_payload(payload):
        return
    sid = str(payload.get("sid") or "").strip()
    if not sid:
        return
    r = await _redis()
    if r is None:
        return
    if not await r.exists(_sid_active_key(sid)):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия завершена. Войдите снова.",
            headers={"WWW-Authenticate": "Bearer"},
        )
