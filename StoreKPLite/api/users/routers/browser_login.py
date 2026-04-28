"""
Вход в миниапп из обычного браузера: одноразовый код в Redis, подтверждение через /start у бота в Telegram.
Refresh в httpOnly cookie + CSRF (как админка).
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import uuid
from datetime import timedelta
from os import getenv
from typing import Optional

import redis.asyncio as redis
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.shared.auth import (
    MINIAPP_ADMIN_ONLY_DETAIL,
    SECRET_KEY,
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    get_user_id_for_request,
)
from api.shared.miniapp_browser_session import (
    activate_miniapp_browser_sid,
    deactivate_miniapp_browser_sid,
    ensure_miniapp_browser_sid_active,
    list_miniapp_browser_sessions_for_user,
    revoke_miniapp_browser_session_for_user,
    upsert_miniapp_browser_session_index,
)
from api.users.database.database import get_session
from api.users.models.admin import Admin
from api.users.models.user import User
from api.users.routers.auth import (
    PLATFORM,
    _apply_telegram_profile,
    _user_payload_for_jwt,
    cache_user_id_for_platform,
)
from api.users.services.runtime_settings import is_miniapp_admin_only

logger = logging.getLogger(__name__)

router = APIRouter()

REDIS_URL = getenv("REDIS_URL", "").strip()
INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")

LOGIN_TTL_SEC = int(getenv("MINIAPP_BROWSER_LOGIN_TTL_SEC", "300"))
REFRESH_DAYS = int(getenv("MINIAPP_BROWSER_REFRESH_TOKEN_EXPIRE_DAYS", "90"))
ACCESS_MINUTES = int(getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
# Привязка одноразового кода к IP клиента на /start: тот же адрес для polling и /complete (защита от перехвата кода на другом устройстве).
MINIAPP_BROWSER_LOGIN_BIND_CLIENT_IP = getenv("MINIAPP_BROWSER_LOGIN_BIND_CLIENT_IP", "true").lower() in {
    "1",
    "true",
    "yes",
}

ADMIN_AUTH_COOKIE_SECURE = getenv("ADMIN_AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}
ADMIN_AUTH_COOKIE_SAMESITE = getenv("ADMIN_AUTH_COOKIE_SAMESITE", "lax").lower()

REDIS_KEY_PREFIX = "timoshka:miniapp_browser_login:"
CODE_RE = re.compile(r"^[a-f0-9]{32}$")

TOKEN_KIND = "miniapp_browser_refresh"
COOKIE_REFRESH = "miniapp_refresh_token"
COOKIE_CSRF = "miniapp_csrf_token"

_redis_client: Optional[redis.Redis] = None


async def _redis() -> redis.Redis:
    global _redis_client
    if not REDIS_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Браузерный вход недоступен (REDIS_URL)",
        )
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _check_internal_token(token: Optional[str]) -> bool:
    exp = (INTERNAL_TOKEN or "").strip()
    if not exp or not token:
        return False
    clean = token.replace("Bearer ", "").strip() if token.startswith("Bearer") else token.strip()
    return secrets.compare_digest(clean, exp)


def _cookie_samesite() -> str:
    v = ADMIN_AUTH_COOKIE_SAMESITE
    if v in {"lax", "strict", "none"}:
        return v
    return "lax"


def _set_refresh_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    max_age = max(1, REFRESH_DAYS * 24 * 60 * 60)
    response.set_cookie(
        key=COOKIE_REFRESH,
        value=refresh_token,
        httponly=True,
        secure=ADMIN_AUTH_COOKIE_SECURE,
        samesite=_cookie_samesite(),
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        key=COOKIE_CSRF,
        value=csrf_token,
        httponly=False,
        secure=ADMIN_AUTH_COOKIE_SECURE,
        samesite=_cookie_samesite(),
        max_age=max_age,
        path="/",
    )


def _clear_refresh_cookies(response: Response) -> None:
    response.delete_cookie(COOKIE_REFRESH, path="/")
    response.delete_cookie(COOKIE_CSRF, path="/")


def _client_ua_ip(http_request: Optional[Request]) -> tuple[str, str]:
    if http_request is None:
        return "", ""
    ua = (http_request.headers.get("user-agent") or "")[:400]
    ip = ""
    if http_request.client:
        ip = (http_request.client.host or "")[:45]
    xff = http_request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            ip = first[:45]
    return ua, ip


def _normalize_client_ip(ip: str) -> str:
    s = (ip or "").strip()[:45]
    if ":" in s:
        return s.lower()
    return s


def _client_ip_matches_binding(stored: object, current: str) -> bool:
    """Совпадение IP с тем, что записали при /start (или отсутствие привязки в старых ключах)."""
    if not MINIAPP_BROWSER_LOGIN_BIND_CLIENT_IP:
        return True
    if stored is None:
        return True
    s = _normalize_client_ip(str(stored))
    c = _normalize_client_ip(current)
    if not s:
        return True
    if not c:
        return False
    return secrets.compare_digest(s, c)


def _effective_poll_status(data: dict, http_request: Request) -> str:
    """Статус для GET /status: не раскрываем ready/forbidden чужому IP."""
    st = data.get("status")
    if st not in ("pending", "ready", "forbidden"):
        return "unknown"
    if _client_ip_matches_binding(data.get("client_ip"), _client_ua_ip(http_request)[1]):
        return st
    if st in ("ready", "forbidden"):
        return "pending"
    return st


def _bot_username() -> str:
    return (getenv("TELEGRAM_BOT_USERNAME") or getenv("BOT_USERNAME") or "").strip().lstrip("@")


async def _load_login_state(code: str) -> Optional[dict]:
    if not CODE_RE.match(code):
        return None
    r = await _redis()
    raw = await r.get(REDIS_KEY_PREFIX + code)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def _replace_login_state(r: redis.Redis, key: str, obj: dict) -> None:
    ttl = await r.ttl(key)
    ex = int(ttl) if ttl is not None and int(ttl) > 0 else LOGIN_TTL_SEC
    await r.set(key, json.dumps(obj), ex=ex)


class BrowserLoginStartResponse(BaseModel):
    code: str
    deep_link: str
    expires_in: int


class BrowserLoginStatusResponse(BaseModel):
    status: str  # pending | ready | forbidden | unknown


class BrowserLoginCompleteBody(BaseModel):
    code: str = Field(..., min_length=32, max_length=32)


class BrowserLoginTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    csrf_token: str
    user_id: int


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


class InternalBrowserLoginConfirm(BaseModel):
    code: str
    telegram_id: int
    first_name: Optional[str] = None
    username: Optional[str] = None


class BrowserSessionItem(BaseModel):
    sid: str
    user_agent: str = ""
    ip: str = ""
    created_at: int
    last_seen: int
    is_current: bool = False


class BrowserSessionListResponse(BaseModel):
    sessions: list[BrowserSessionItem]


async def _issue_tokens_for_user(
    user: User,
    response: Response,
    session: AsyncSession,
    http_request: Optional[Request] = None,
) -> BrowserLoginTokenResponse:
    admin_result = await session.execute(select(Admin).where(Admin.user_id == user.id))
    admin = admin_result.scalar_one_or_none()
    if await is_miniapp_admin_only(session) and admin is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MINIAPP_ADMIN_ONLY_DETAIL)

    payload = _user_payload_for_jwt(user)
    if admin:
        at = (admin.admin_type or "").strip()
        payload["admin_type"] = at if at else "staff"

    sid = uuid.uuid4().hex
    csrf_token = secrets.token_urlsafe(32)
    access = create_access_token(
        data=payload,
        expires_delta=timedelta(minutes=ACCESS_MINUTES),
    )
    refresh = create_refresh_token(
        data={
            "sub": str(user.id),
            "token_kind": TOKEN_KIND,
            "sid": sid,
            "csrf": csrf_token,
        },
        expires_delta=timedelta(days=REFRESH_DAYS),
    )
    ttl = REFRESH_DAYS + 7
    await activate_miniapp_browser_sid(sid, ttl_days=ttl)
    ua, ip = _client_ua_ip(http_request)
    await upsert_miniapp_browser_session_index(user.id, sid, ua, ip, ttl_days=ttl)
    _set_refresh_cookies(response, refresh, csrf_token)
    await cache_user_id_for_platform(user.id, PLATFORM, user.tgid)
    return BrowserLoginTokenResponse(
        access_token=access,
        csrf_token=csrf_token,
        user_id=user.id,
    )


@router.post("/auth/browser-login/start", response_model=BrowserLoginStartResponse)
async def browser_login_start(http_request: Request):
    """Создать одноразовый код и ссылку t.me/bot?start=weblogin_<code>."""
    await _redis()
    code = secrets.token_hex(16)
    if not CODE_RE.match(code):
        raise HTTPException(status_code=500, detail="internal")
    r = await _redis()
    key = REDIS_KEY_PREFIX + code
    _, client_ip = _client_ua_ip(http_request)
    payload = {"v": 1, "status": "pending", "client_ip": client_ip}
    await r.set(key, json.dumps(payload), ex=LOGIN_TTL_SEC)
    uname = _bot_username()
    if not uname:
        logger.warning("TELEGRAM_BOT_USERNAME не задан — deep_link будет неверным")
    deep_link = f"https://t.me/{uname or 'bot'}?start=weblogin_{code}"
    return BrowserLoginStartResponse(code=code, deep_link=deep_link, expires_in=LOGIN_TTL_SEC)


@router.get("/auth/browser-login/status", response_model=BrowserLoginStatusResponse)
async def browser_login_status(code: str, http_request: Request):
    if not CODE_RE.match(code):
        return BrowserLoginStatusResponse(status="unknown")
    data = await _load_login_state(code)
    if not data:
        return BrowserLoginStatusResponse(status="unknown")
    st = _effective_poll_status(data, http_request)
    if st in ("pending", "ready", "forbidden"):
        return BrowserLoginStatusResponse(status=st)
    return BrowserLoginStatusResponse(status="unknown")


@router.post("/auth/browser-login/complete", response_model=BrowserLoginTokenResponse)
async def browser_login_complete(
    body: BrowserLoginCompleteBody,
    response: Response,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Обменять подтверждённый код на access + cookies refresh/csrf (один раз)."""
    if not CODE_RE.match(body.code):
        raise HTTPException(status_code=400, detail="Неверный код")
    r = await _redis()
    key = REDIS_KEY_PREFIX + body.code
    raw = await r.get(key)
    if not raw:
        raise HTTPException(status_code=400, detail="Код недействителен или истёк")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Код недействителен")

    if data.get("status") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MINIAPP_ADMIN_ONLY_DETAIL)
    if data.get("status") != "ready":
        raise HTTPException(status_code=400, detail="Вход ещё не подтверждён в Telegram")
    if not _client_ip_matches_binding(data.get("client_ip"), _client_ua_ip(http_request)[1]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Завершить вход можно только с того же устройства или сети, с которого он был начат. Откройте сайт заново и повторите вход.",
        )
    user_id = data.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=400, detail="Код недействителен")

    deleted = await r.delete(key)
    if not deleted:
        raise HTTPException(status_code=400, detail="Код уже использован")

    result = await session.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Пользователь не найден")
    return await _issue_tokens_for_user(user, response, session, http_request)


@router.get("/auth/browser-login/sessions", response_model=BrowserSessionListResponse)
async def browser_login_list_sessions(
    user_id: int = Depends(get_user_id_for_request),
    refresh_cookie: Optional[str] = Cookie(None, alias=COOKIE_REFRESH),
):
    """Активные браузерные сессии (устройства) текущего пользователя."""
    current_sid = ""
    if refresh_cookie:
        try:
            payload = jwt.decode(refresh_cookie, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("token_kind") == TOKEN_KIND:
                try:
                    if int(payload.get("sub")) == int(user_id):
                        current_sid = str(payload.get("sid") or "").strip()
                except (TypeError, ValueError):
                    pass
        except JWTError:
            pass
    raw = await list_miniapp_browser_sessions_for_user(user_id)
    items = [
        BrowserSessionItem(
            sid=x["sid"],
            user_agent=x["user_agent"],
            ip=x["ip"],
            created_at=x["created_at"],
            last_seen=x["last_seen"],
            is_current=(x["sid"] == current_sid and bool(current_sid)),
        )
        for x in raw
    ]
    return BrowserSessionListResponse(sessions=items)


@router.post("/auth/browser-login/sessions/{sid}/revoke")
async def browser_login_revoke_session(
    sid: str,
    user_id: int = Depends(get_user_id_for_request),
):
    if not sid or len(sid) > 80:
        raise HTTPException(status_code=400, detail="Неверный идентификатор сессии")
    ok = await revoke_miniapp_browser_session_for_user(user_id, sid)
    if not ok:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return {"ok": True}


@router.post("/auth/browser-login/refresh", response_model=BrowserLoginTokenResponse)
async def browser_login_refresh(
    response: Response,
    http_request: Request,
    refresh_body: Optional[RefreshRequest] = None,
    csrf_header: Optional[str] = Header(None, alias="X-CSRF-Token"),
    refresh_cookie: Optional[str] = Cookie(None, alias=COOKIE_REFRESH),
    session: AsyncSession = Depends(get_session),
):
    incoming = (refresh_body.refresh_token if refresh_body is not None else None) or refresh_cookie
    if not incoming:
        raise HTTPException(status_code=401, detail="Невалидный refresh токен")
    if not csrf_header:
        raise HTTPException(status_code=403, detail="CSRF проверка не пройдена")
    try:
        payload = jwt.decode(incoming, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Невалидный refresh токен")
    if payload.get("token_kind") != TOKEN_KIND:
        raise HTTPException(status_code=401, detail="Невалидный refresh токен")
    await ensure_miniapp_browser_sid_active(payload)

    uid_raw = payload.get("sub")
    try:
        user_id = int(uid_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Невалидный refresh токен")

    token_csrf = str(payload.get("csrf") or "").strip()
    if not token_csrf or token_csrf != csrf_header:
        raise HTTPException(status_code=403, detail="CSRF проверка не пройдена")

    sid = (payload.get("sid") or "").strip() or uuid.uuid4().hex

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    admin_row = (
        await session.execute(select(Admin).where(Admin.user_id == user.id))
    ).scalar_one_or_none()
    if await is_miniapp_admin_only(session) and admin_row is None:
        _clear_refresh_cookies(response)
        await deactivate_miniapp_browser_sid(sid)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MINIAPP_ADMIN_ONLY_DETAIL)

    jwt_payload = _user_payload_for_jwt(user)
    if admin_row:
        at = (admin_row.admin_type or "").strip()
        jwt_payload["admin_type"] = at if at else "staff"
    access = create_access_token(
        data=jwt_payload,
        expires_delta=timedelta(minutes=ACCESS_MINUTES),
    )
    refresh = create_refresh_token(
        data={
            "sub": str(user.id),
            "token_kind": TOKEN_KIND,
            "sid": sid,
            "csrf": token_csrf,
        },
        expires_delta=timedelta(days=REFRESH_DAYS),
    )
    ttl = REFRESH_DAYS + 7
    await activate_miniapp_browser_sid(sid, ttl_days=ttl)
    ua, ip = _client_ua_ip(http_request)
    await upsert_miniapp_browser_session_index(user.id, sid, ua, ip, ttl_days=ttl)
    _set_refresh_cookies(response, refresh, token_csrf)
    return BrowserLoginTokenResponse(access_token=access, csrf_token=token_csrf, user_id=user.id)


@router.post("/auth/browser-login/logout")
async def browser_login_logout(
    response: Response,
    refresh_body: Optional[RefreshRequest] = None,
    csrf_header: Optional[str] = Header(None, alias="X-CSRF-Token"),
    refresh_cookie: Optional[str] = Cookie(None, alias=COOKIE_REFRESH),
):
    incoming = (refresh_body.refresh_token if refresh_body is not None else None) or refresh_cookie
    if incoming:
        try:
            payload = jwt.decode(incoming, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("token_kind") == TOKEN_KIND:
                token_csrf = str(payload.get("csrf") or "").strip()
                if csrf_header and token_csrf and token_csrf == csrf_header:
                    sid = str(payload.get("sid") or "").strip()
                    if sid:
                        await deactivate_miniapp_browser_sid(sid)
        except JWTError:
            pass
    _clear_refresh_cookies(response)
    return {"ok": True}


@router.post("/internal/browser-login/confirm")
async def internal_browser_login_confirm(
    body: InternalBrowserLoginConfirm,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    session: AsyncSession = Depends(get_session),
):
    """Вызывается ботом после /start weblogin_<code>."""
    if not _check_internal_token(x_internal_token or ""):
        raise HTTPException(status_code=401, detail="Неверный внутренний токен")
    code = (body.code or "").strip()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=400, detail="Неверный код")
    r = await _redis()
    key = REDIS_KEY_PREFIX + code
    raw = await r.get(key)
    if not raw:
        raise HTTPException(status_code=404, detail="Код не найден или истёк")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Неверный код")
    if data.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Код уже обработан")

    tid = int(body.telegram_id)
    result = await session.execute(select(User).where(User.tgid == tid))
    user = result.scalar_one_or_none()
    is_new = False
    if not user:
        user = User(tgid=tid)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        is_new = True
    if _apply_telegram_profile(user, body.first_name, body.username):
        await session.commit()
        await session.refresh(user)

    admin_result = await session.execute(select(Admin).where(Admin.user_id == user.id))
    admin = admin_result.scalar_one_or_none()
    if await is_miniapp_admin_only(session) and admin is None:
        nxt = {"v": 1, "status": "forbidden"}
        if "client_ip" in data:
            nxt["client_ip"] = data["client_ip"]
        await _replace_login_state(r, key, nxt)
        return {"ok": True, "status": "forbidden", "is_new_user": is_new}

    nxt = {"v": 1, "status": "ready", "user_id": user.id}
    if "client_ip" in data:
        nxt["client_ip"] = data["client_ip"]
    await _replace_login_state(r, key, nxt)
    await cache_user_id_for_platform(user.id, PLATFORM, tid)
    return {"ok": True, "status": "ready", "is_new_user": is_new}
