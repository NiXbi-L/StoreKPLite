"""
Активные сессии браузерного входа в миниапп (refresh JWT с token_kind=miniapp_browser_refresh).
По смыслу как admin_sid: revoke через удаление ключа в Redis.
Индекс user_id → sid и метаданные — для списка «устройств» в профиле.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from os import getenv
from typing import Any, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = getenv("REDIS_URL", "").strip()

_client: Optional[redis.Redis] = None


def _sid_active_key(sid: str) -> str:
    return f"timoshka:miniapp_browser_sid_active:{sid}"


def _user_sids_key(user_id: int) -> str:
    return f"timoshka:miniapp_browser_user_sids:{int(user_id)}"


def _session_meta_key(sid: str) -> str:
    return f"timoshka:miniapp_browser_session_meta:{sid}"


async def _redis() -> Optional[redis.Redis]:
    global _client
    if not REDIS_URL:
        return None
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


async def activate_miniapp_browser_sid(sid: str, ttl_days: int = 120) -> None:
    s = (sid or "").strip()
    if not s:
        return
    r = await _redis()
    if r is None:
        return
    await r.set(_sid_active_key(s), "1", ex=timedelta(days=max(1, int(ttl_days))))


async def upsert_miniapp_browser_session_index(
    user_id: int,
    sid: str,
    user_agent: str = "",
    client_ip: str = "",
    *,
    ttl_days: int = 120,
) -> None:
    """Индекс сессий пользователя + метаданные (UA, IP, время)."""
    s = (sid or "").strip()
    if not s:
        return
    r = await _redis()
    if r is None:
        return
    uid = int(user_id)
    now = str(int(time.time()))
    await r.sadd(_user_sids_key(uid), s)
    meta_k = _session_meta_key(s)
    await r.hsetnx(meta_k, "created_at", now)
    await r.hset(
        meta_k,
        mapping={
            "user_id": str(uid),
            "user_agent": (user_agent or "")[:400],
            "ip": (client_ip or "")[:45],
            "last_seen": now,
        },
    )
    ex_sec = int(timedelta(days=max(1, int(ttl_days) + 14)).total_seconds())
    await r.expire(meta_k, ex_sec)


async def deactivate_miniapp_browser_sid(sid: str) -> None:
    s = (sid or "").strip()
    if not s:
        return
    r = await _redis()
    if r is None:
        return
    meta_k = _session_meta_key(s)
    meta = await r.hgetall(meta_k)
    uid_raw = meta.get("user_id")
    await r.delete(_sid_active_key(s))
    await r.delete(meta_k)
    if uid_raw:
        try:
            await r.srem(_user_sids_key(int(uid_raw)), s)
        except (TypeError, ValueError):
            pass


async def list_miniapp_browser_sessions_for_user(user_id: int) -> list[dict[str, Any]]:
    """Только активные (есть ключ sid_active) с метаданными."""
    r = await _redis()
    if r is None:
        return []
    uid = int(user_id)
    sids = await r.smembers(_user_sids_key(uid))
    out: list[dict[str, Any]] = []
    for sid in sids or []:
        if not isinstance(sid, str):
            sid = str(sid)
        if not await r.exists(_sid_active_key(sid)):
            continue
        meta = await r.hgetall(_session_meta_key(sid))
        if not meta:
            continue
        try:
            created = int(meta.get("created_at") or 0)
        except (TypeError, ValueError):
            created = 0
        try:
            last_seen = int(meta.get("last_seen") or created)
        except (TypeError, ValueError):
            last_seen = created
        out.append(
            {
                "sid": sid,
                "user_agent": meta.get("user_agent") or "",
                "ip": meta.get("ip") or "",
                "created_at": created,
                "last_seen": last_seen,
            }
        )
    out.sort(key=lambda x: x["last_seen"], reverse=True)
    return out


async def revoke_miniapp_browser_session_for_user(user_id: int, sid: str) -> bool:
    s = (sid or "").strip()
    if not s:
        return False
    r = await _redis()
    if r is None:
        return False
    uid = int(user_id)
    if not await r.sismember(_user_sids_key(uid), s):
        return False
    await deactivate_miniapp_browser_sid(s)
    return True


async def ensure_miniapp_browser_sid_active(payload: dict) -> None:
    """Для refresh-токена миниаппа из браузера: sid должен быть активен в Redis."""
    from fastapi import HTTPException, status

    if payload.get("token_kind") != "miniapp_browser_refresh":
        return
    sid = str(payload.get("sid") or "").strip()
    if not sid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный refresh токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    r = await _redis()
    if r is None:
        return
    if not await r.exists(_sid_active_key(sid)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия завершена. Войдите снова.",
            headers={"WWW-Authenticate": "Bearer"},
        )
