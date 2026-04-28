"""
Роутер для админского доступа (JWT авторизация)
"""
import base64
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from os import getenv

import httpx
from fastapi import APIRouter, Depends, HTTPException, Form, Query, Request, Response, Header, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from pydantic import BaseModel, field_validator
from passlib.context import CryptContext
from typing import Optional

from api.users.database.database import get_session

logger = logging.getLogger(__name__)

PRODUCTS_SERVICE_URL = getenv("PRODUCTS_SERVICE_URL", "http://products-service:8002")
FINANCE_SERVICE_URL = getenv("FINANCE_SERVICE_URL", "http://finance-service:8003")
DELIVERY_SERVICE_URL = getenv("DELIVERY_SERVICE_URL", "http://delivery-service:8005")
SUPPORT_SERVICE_URL = getenv("SUPPORT_SERVICE_URL", "http://support-service:8004")
INTERNAL_TOKEN = getenv("INTERNAL_TOKEN", "internal-secret-token-change-in-production")
from api.users.models.user import User
from api.users.models.admin import Admin
from api.users.models.admin_role import AdminRole
from api.users.models.admin_session import AdminSession
from jose import JWTError, jwt
from api.shared.auth import (
    create_access_token,
    create_refresh_token,
    verify_jwt_token,
    SECRET_KEY,
    ALGORITHM,
)
from api.shared.admin_jwt_rev import (
    activate_admin_sid,
    bump_admin_jwt_rev,
    bump_admin_jwt_rev_many,
    deactivate_admin_sid,
    get_admin_jwt_rev_for_login,
)
from api.shared.jwt_admin_deps import require_jwt_permission
from api.shared.admin_permissions import (
    normalize_permissions_payload,
    owner_permissions_dict,
    parse_permissions_json,
    permission_catalog_public,
)

router = APIRouter()

# Сообщения для клиента без раскрытия причины отказа (логин/пароль/токен/CSRF и т.д.)
PUBLIC_ADMIN_LOGIN_FAILED = "Не удалось войти. Проверьте данные и попробуйте снова."
PUBLIC_ADMIN_SESSION_INVALID = "Не удалось продолжить сессию. Войдите снова."
PUBLIC_ADMIN_ACCESS_INVALID = "Требуется авторизация."

# Настройки хэширования паролей
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated="auto",
    pbkdf2_sha256__default_rounds=29000
)
ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES = int(getenv("ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days
ADMIN_REFRESH_TOKEN_EXPIRE_DAYS = int(getenv("ADMIN_REFRESH_TOKEN_EXPIRE_DAYS", "90"))  # 90 days
ADMIN_AUTH_COOKIE_SECURE = getenv("ADMIN_AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}
ADMIN_AUTH_COOKIE_SAMESITE = getenv("ADMIN_AUTH_COOKIE_SAMESITE", "lax").lower()


class AdminAuthOkBody(BaseModel):
    """Ответ входа/refresh: без токенов в JSON — access и refresh только в httpOnly cookies."""

    user_id: int
    admin_type: str
    role_title: Optional[str] = None
    permissions: Optional[dict] = None


def get_password_hash(password: str) -> str:
    """Хэширование пароля"""
    return pwd_context.hash(password)


async def _create_admin_access_token(admin_row: Admin, claims: dict, sid: str) -> str:
    arv = await get_admin_jwt_rev_for_login(admin_row.user_id)
    return create_access_token(
        data={
            "sub": str(admin_row.user_id),
            "login": admin_row.login,
            "sid": sid,
            **claims,
            "arv": arv,
        },
        expires_delta=timedelta(minutes=ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


async def _create_admin_refresh_token(admin_row: Admin, sid: str, csrf_token: str) -> str:
    arv = await get_admin_jwt_rev_for_login(admin_row.user_id)
    return create_refresh_token(
        data={
            "sub": str(admin_row.user_id),
            "login": admin_row.login,
            "sid": sid,
            "token_kind": "admin_refresh",
            "csrf": csrf_token,
            "arv": arv,
        },
        expires_delta=timedelta(days=ADMIN_REFRESH_TOKEN_EXPIRE_DAYS),
    )


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


def _cookie_samesite() -> str:
    v = ADMIN_AUTH_COOKIE_SAMESITE
    if v in {"lax", "strict", "none"}:
        return v
    return "lax"


def _set_refresh_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    max_age = max(1, ADMIN_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)
    response.set_cookie(
        key="admin_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=ADMIN_AUTH_COOKIE_SECURE,
        samesite=_cookie_samesite(),
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        key="admin_csrf_token",
        value=csrf_token,
        httponly=False,
        secure=ADMIN_AUTH_COOKIE_SECURE,
        samesite=_cookie_samesite(),
        max_age=max_age,
        path="/",
    )


def _clear_refresh_cookies(response: Response) -> None:
    response.delete_cookie("admin_refresh_token", path="/")
    response.delete_cookie("admin_csrf_token", path="/")


def _set_admin_access_cookie(response: Response, access_token: str) -> None:
    max_age = max(60, int(ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES) * 60)
    response.set_cookie(
        key="admin_access_token",
        value=access_token,
        httponly=True,
        secure=ADMIN_AUTH_COOKIE_SECURE,
        samesite=_cookie_samesite(),
        max_age=max_age,
        path="/",
    )


def _clear_admin_access_cookie(response: Response) -> None:
    response.delete_cookie("admin_access_token", path="/")


def _decode_credentials_blob(blob: str) -> tuple[str, str]:
    """Base64(JSON {login, password}) — UTF-8."""
    blob = (blob or "").strip()
    if not blob:
        return "", ""
    pad = "=" * (-len(blob) % 4)
    try:
        raw = base64.b64decode(blob + pad, validate=False)
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return "", ""
    if not isinstance(obj, dict):
        return "", ""
    return str(obj.get("login") or "").strip(), str(obj.get("password") or "")


def _decode_optional_base64_password_field(value: Optional[str]) -> Optional[str]:
    """Клиент может передавать пароль как base64(utf-8); иначе — как раньше открытым текстом."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    pad = "=" * (-len(s) % 4)
    try:
        raw = base64.b64decode(s + pad, validate=False)
        out = raw.decode("utf-8")
        return out if out else s
    except Exception:
        return s


class AdminSessionItem(BaseModel):
    sid: str
    created_at: str
    last_seen_at: str
    revoked_at: Optional[str] = None
    is_current: bool
    ip: Optional[str] = None
    user_agent: Optional[str] = None


class AdminSessionListResponse(BaseModel):
    sessions: list[AdminSessionItem]
    current_sid: Optional[str] = None


class AdminSessionActionResponse(BaseModel):
    success: bool = True
    affected: int = 0


def _extract_request_ip(request: Request) -> Optional[str]:
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    if request.client and request.client.host:
        return request.client.host
    return None


async def _upsert_admin_session(
    session: AsyncSession,
    user_id: int,
    sid: str,
    request: Request,
) -> AdminSession:
    row = (await session.execute(select(AdminSession).where(AdminSession.sid == sid))).scalar_one_or_none()
    ua = (request.headers.get("user-agent") or "").strip() or None
    ip = _extract_request_ip(request)
    now = datetime.now(timezone.utc)
    if row is None:
        row = AdminSession(
            user_id=user_id,
            sid=sid,
            user_agent=ua,
            ip=ip,
            created_at=now,
            last_seen_at=now,
            revoked_at=None,
        )
        session.add(row)
    else:
        row.user_id = user_id
        row.user_agent = ua
        row.ip = ip
        row.last_seen_at = now
        row.revoked_at = None
    await session.commit()
    await session.refresh(row)
    return row


async def _parse_admin_login_credentials(request: Request) -> tuple[str, str]:
    """Логин/пароль: поле `credentials` (base64 JSON) или пары login+password в JSON/form."""
    ct = (request.headers.get("content-type") or "").lower()
    login, password = "", ""
    try:
        if "application/json" in ct:
            raw = await request.json()
            if isinstance(raw, dict):
                cred = raw.get("credentials")
                if cred is not None and str(cred).strip():
                    login, password = _decode_credentials_blob(str(cred))
                else:
                    login = str(raw.get("login") or "").strip()
                    password = str(raw.get("password") or "")
        elif "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
            form = await request.form()
            cred = form.get("credentials")
            if cred is not None and str(cred).strip():
                login, password = _decode_credentials_blob(str(cred))
            else:
                login = str(form.get("login") or "").strip()
                password = str(form.get("password") or "")
    except Exception:
        logger.debug("admin login: failed to parse body", exc_info=True)
    return login, password


async def _resolve_admin_claims(session: AsyncSession, admin_row: Admin) -> dict:
    """Поля JWT: owner — полный доступ; staff — из admin_roles или legacy permissions_json."""
    if (admin_row.admin_type or "").strip().lower() == "owner":
        return {
            "admin_type": "owner",
            "role_title": admin_row.role_title or "Владелец",
            "permissions": owner_permissions_dict(),
        }
    role_row = None
    if admin_row.role_id is not None:
        role_row = await session.get(AdminRole, admin_row.role_id)
    if role_row is not None:
        return {
            "admin_type": "staff",
            "role_title": (role_row.name or "").strip() or "Сотрудник",
            "permissions": parse_permissions_json(role_row.permissions_json),
        }
    return {
        "admin_type": "staff",
        "role_title": (admin_row.role_title or "").strip() or "Сотрудник",
        "permissions": parse_permissions_json(admin_row.permissions_json),
    }


@router.post("/admin/login", response_model=AdminAuthOkBody)
async def admin_login(
    http_request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """
    Вход админа по логину и паролю (получение JWT токена).

    Тело: предпочтительно один параметр `credentials` = base64(JSON UTF-8 `{"login","password"}`),
    либо JSON/form с полями `login` и `password`. Access и refresh — только в httpOnly cookies.

    Суперпользователь-владелец: логин и пароль задаются в OWNER_LOGIN и OWNER_PASSWORD;
    при первом входе запись создаётся/подтягивается по OWNER_ID (tgid пользователя).
    Если OWNER_PASSWORD не задан, этот путь отключён (вход только по паролю из БД).
    """
    login, password = await _parse_admin_login_credentials(http_request)
    if not login or password == "":
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_LOGIN_FAILED)

    owner_id = int(getenv("OWNER_ID", "0"))
    owner_login = (getenv("OWNER_LOGIN", "Owner") or "Owner").strip() or "Owner"
    owner_password = (getenv("OWNER_PASSWORD") or "").strip()

    if owner_password and login == owner_login and password == owner_password:
        owner_result = await session.execute(
            select(Admin).where(Admin.login == owner_login)
        )
        owner = owner_result.scalar_one_or_none()

        if not owner:
            if owner_id > 0:
                user_result = await session.execute(
                    select(User).where(User.tgid == owner_id)
                )
                user = user_result.scalar_one_or_none()

                if user:
                    admin_result = await session.execute(
                        select(Admin).where(Admin.user_id == user.id, Admin.admin_type == "owner")
                    )
                    owner = admin_result.scalar_one_or_none()

                if not owner:
                    if not user:
                        user = User(tgid=owner_id)
                        session.add(user)
                        await session.commit()
                        await session.refresh(user)

                    owner = Admin(
                        user_id=user.id,
                        admin_type="owner",
                        login=owner_login,
                        password=get_password_hash(owner_password),
                    )
                    session.add(owner)
                    await session.commit()
                    await session.refresh(owner)
                else:
                    if not owner.login:
                        owner.login = owner_login
                    owner.password = get_password_hash(owner_password)
                    await session.commit()
                    await session.refresh(owner)
        else:
            owner.password = get_password_hash(owner_password)
            await session.commit()
            await session.refresh(owner)

        if owner is None:
            raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_LOGIN_FAILED)

        sid = uuid.uuid4().hex
        csrf_token = uuid.uuid4().hex
        await _upsert_admin_session(session, owner.user_id, sid, http_request)
        await activate_admin_sid(sid, ttl_days=ADMIN_REFRESH_TOKEN_EXPIRE_DAYS + 7)
        claims = await _resolve_admin_claims(session, owner)
        access_token = await _create_admin_access_token(owner, claims, sid)
        refresh_token = await _create_admin_refresh_token(owner, sid, csrf_token)
        _set_refresh_cookies(response, refresh_token, csrf_token)
        _set_admin_access_cookie(response, access_token)

        return AdminAuthOkBody(
            user_id=owner.user_id,
            admin_type=claims["admin_type"],
            role_title=claims.get("role_title"),
            permissions=claims.get("permissions"),
        )

    # Обычная авторизация по логину
    result = await session.execute(
        select(Admin).where(Admin.login == login)
    )
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_LOGIN_FAILED)

    if not admin.password:
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_LOGIN_FAILED)

    try:
        if not pwd_context.verify(password, admin.password):
            raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_LOGIN_FAILED)
    except HTTPException:
        raise
    except (ValueError, Exception):
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_LOGIN_FAILED)
    
    sid = uuid.uuid4().hex
    csrf_token = uuid.uuid4().hex
    await _upsert_admin_session(session, admin.user_id, sid, http_request)
    await activate_admin_sid(sid, ttl_days=ADMIN_REFRESH_TOKEN_EXPIRE_DAYS + 7)
    claims = await _resolve_admin_claims(session, admin)
    access_token = await _create_admin_access_token(admin, claims, sid)
    refresh_token = await _create_admin_refresh_token(admin, sid, csrf_token)
    _set_refresh_cookies(response, refresh_token, csrf_token)
    _set_admin_access_cookie(response, access_token)

    return AdminAuthOkBody(
        user_id=admin.user_id,
        admin_type=claims["admin_type"],
        role_title=claims.get("role_title"),
        permissions=claims.get("permissions"),
    )


@router.post("/admin/refresh", response_model=AdminAuthOkBody)
async def admin_refresh_token(
    http_request: Request,
    response: Response,
    request: Optional[RefreshRequest] = None,
    csrf_header: Optional[str] = Header(None, alias="X-CSRF-Token"),
    refresh_cookie: Optional[str] = Cookie(None, alias="admin_refresh_token"),
    csrf_cookie: Optional[str] = Cookie(None, alias="admin_csrf_token"),
    session: AsyncSession = Depends(get_session),
):
    """Обновить access_token по refresh_token без повторного ввода логина/пароля."""
    incoming_refresh = (request.refresh_token if request is not None else None) or refresh_cookie
    if not incoming_refresh:
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_SESSION_INVALID)
    if not csrf_header:
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_SESSION_INVALID)
    try:
        payload = jwt.decode(incoming_refresh, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_SESSION_INVALID)

    if payload.get("token_kind") != "admin_refresh":
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_SESSION_INVALID)

    uid_raw = payload.get("sub")
    try:
        user_id = int(uid_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_SESSION_INVALID)
    sid = (payload.get("sid") or "").strip()
    if not sid:
        # Поддержка старых refresh без sid: при первом успешном refresh выдаём sid.
        sid = uuid.uuid4().hex

    admin = (
        await session.execute(select(Admin).where(Admin.user_id == user_id))
    ).scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_SESSION_INVALID)

    token_csrf = str(payload.get("csrf") or "").strip()
    if not token_csrf or token_csrf != csrf_header:
        raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_SESSION_INVALID)

    sess = (await session.execute(select(AdminSession).where(AdminSession.sid == sid))).scalar_one_or_none()
    if sess is not None:
        if sess.user_id != user_id:
            raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_SESSION_INVALID)
        if sess.revoked_at is not None:
            raise HTTPException(status_code=401, detail=PUBLIC_ADMIN_SESSION_INVALID)

    await _upsert_admin_session(session, user_id, sid, http_request)
    await activate_admin_sid(sid, ttl_days=ADMIN_REFRESH_TOKEN_EXPIRE_DAYS + 7)
    claims = await _resolve_admin_claims(session, admin)
    new_csrf_token = token_csrf
    access_token = await _create_admin_access_token(admin, claims, sid)
    refresh_token = await _create_admin_refresh_token(admin, sid, new_csrf_token)
    if response is not None:
        _set_refresh_cookies(response, refresh_token, new_csrf_token)
        _set_admin_access_cookie(response, access_token)
    return AdminAuthOkBody(
        user_id=admin.user_id,
        admin_type=claims["admin_type"],
        role_title=claims.get("role_title"),
        permissions=claims.get("permissions"),
    )


@router.get("/admin/me")
async def get_admin_info(
    user_data: dict = Depends(verify_jwt_token),
    session: AsyncSession = Depends(get_session)
):
    """Получить информацию о текущем админе"""
    user_id = user_data["user_id"]
    
    result = await session.execute(
        select(Admin).where(Admin.user_id == user_id)
    )
    admin = result.scalar_one_or_none()
    
    if not admin:
        raise HTTPException(status_code=404, detail="Админ не найден")
    
    # Получаем пользователя
    user_result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    
    claims = await _resolve_admin_claims(session, admin)
    return {
        "user_id": admin.user_id,
        "admin_type": claims["admin_type"],
        "role_title": claims.get("role_title"),
        "permissions": claims.get("permissions"),
        "role_id": admin.role_id,
        "login": admin.login,
        "tgid": user.tgid if user else None,
    }


@router.get("/admin/sessions", response_model=AdminSessionListResponse)
async def list_admin_sessions(
    user_data: dict = Depends(verify_jwt_token),
    session: AsyncSession = Depends(get_session),
):
    user_id = user_data["user_id"]
    current_sid = user_data.get("sid")
    if isinstance(current_sid, str):
        current_sid = current_sid.strip() or None
    rows = (
        await session.execute(
            select(AdminSession)
            .where(
                AdminSession.user_id == user_id,
                AdminSession.revoked_at.is_(None),
            )
            .order_by(AdminSession.created_at.desc())
        )
    ).scalars().all()

    def _ts(v: Optional[datetime]) -> str:
        return v.isoformat() if v else ""

    return AdminSessionListResponse(
        current_sid=current_sid,
        sessions=[
            AdminSessionItem(
                sid=r.sid,
                created_at=_ts(r.created_at),
                last_seen_at=_ts(r.last_seen_at),
                revoked_at=r.revoked_at.isoformat() if r.revoked_at else None,
                is_current=bool(current_sid and r.sid == current_sid),
                ip=r.ip,
                user_agent=r.user_agent,
            )
            for r in rows
        ],
    )


@router.post("/admin/sessions/{sid}/revoke", response_model=AdminSessionActionResponse)
async def revoke_admin_session(
    sid: str,
    user_data: dict = Depends(verify_jwt_token),
    session: AsyncSession = Depends(get_session),
):
    user_id = user_data["user_id"]
    sid = (sid or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Укажите sid")
    row = (await session.execute(select(AdminSession).where(AdminSession.sid == sid))).scalar_one_or_none()
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await deactivate_admin_sid(row.sid)
        await session.commit()
        return AdminSessionActionResponse(affected=1)
    return AdminSessionActionResponse(affected=0)


@router.post("/admin/sessions/revoke-newer", response_model=AdminSessionActionResponse)
async def revoke_newer_admin_sessions(
    user_data: dict = Depends(verify_jwt_token),
    session: AsyncSession = Depends(get_session),
):
    user_id = user_data["user_id"]
    current_sid = str(user_data.get("sid") or "").strip()
    if not current_sid:
        return AdminSessionActionResponse(affected=0)

    current = (
        await session.execute(
            select(AdminSession).where(
                AdminSession.user_id == user_id,
                AdminSession.sid == current_sid,
            )
        )
    ).scalar_one_or_none()
    if current is None:
        return AdminSessionActionResponse(affected=0)

    rows = (
        await session.execute(
            select(AdminSession).where(
                AdminSession.user_id == user_id,
                AdminSession.revoked_at.is_(None),
                AdminSession.created_at > current.created_at,
            )
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.revoked_at = now
        await deactivate_admin_sid(row.sid)
    if rows:
        await session.commit()
    return AdminSessionActionResponse(affected=len(rows))


@router.post("/admin/sessions/revoke-older", response_model=AdminSessionActionResponse)
async def revoke_older_admin_sessions(
    days: int = Query(7, ge=1, le=365),
    user_data: dict = Depends(verify_jwt_token),
    session: AsyncSession = Depends(get_session),
):
    user_id = user_data["user_id"]
    current_sid = str(user_data.get("sid") or "").strip()
    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await session.execute(
            select(AdminSession).where(
                AdminSession.user_id == user_id,
                AdminSession.revoked_at.is_(None),
                AdminSession.created_at < threshold,
                AdminSession.sid != current_sid,
            )
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.revoked_at = now
        await deactivate_admin_sid(row.sid)
    if rows:
        await session.commit()
    return AdminSessionActionResponse(affected=len(rows))


@router.post("/admin/sessions/revoke-others", response_model=AdminSessionActionResponse)
async def revoke_other_admin_sessions(
    user_data: dict = Depends(verify_jwt_token),
    session: AsyncSession = Depends(get_session),
):
    user_id = user_data["user_id"]
    current_sid = str(user_data.get("sid") or "").strip()
    if not current_sid:
        return AdminSessionActionResponse(affected=0)
    rows = (
        await session.execute(
            select(AdminSession).where(
                AdminSession.user_id == user_id,
                AdminSession.revoked_at.is_(None),
                AdminSession.sid != current_sid,
            )
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.revoked_at = now
        await deactivate_admin_sid(row.sid)
    if rows:
        await session.commit()
    return AdminSessionActionResponse(affected=len(rows))


@router.post("/admin/logout")
async def admin_logout(
    response: Response,
    user_data: dict = Depends(verify_jwt_token),
    session: AsyncSession = Depends(get_session),
):
    """Явный выход: завершает текущую сессию (sid) и чистит auth cookies."""
    sid = str(user_data.get("sid") or "").strip()
    if sid:
        row = (await session.execute(select(AdminSession).where(AdminSession.sid == sid))).scalar_one_or_none()
        if row and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            await session.commit()
        await deactivate_admin_sid(sid)
    _clear_refresh_cookies(response)
    _clear_admin_access_cookie(response)
    return {"ok": True}


# Dependency для проверки прав админа
async def get_current_admin(
    user_data: dict = Depends(verify_jwt_token),
    session: AsyncSession = Depends(get_session)
) -> Admin:
    """Получить текущего админа с проверкой прав"""
    user_id = user_data["user_id"]
    
    result = await session.execute(
        select(Admin).where(Admin.user_id == user_id)
    )
    admin = result.scalar_one_or_none()
    
    if not admin:
        raise HTTPException(status_code=404, detail="Админ не найден")
    
    return admin


async def require_owner(
    admin: Admin = Depends(get_current_admin)
) -> Admin:
    """Проверка, что текущий админ - владелец"""
    if admin.admin_type != "owner":
        raise HTTPException(status_code=403, detail="Только владелец может выполнить это действие")
    return admin


# ========== Эндпоинты для работы с пользователями ==========

class UserListResponse(BaseModel):
    id: int
    tgid: Optional[int] = None
    firstname: Optional[str] = None
    username: Optional[str] = None
    country_code: Optional[str] = None
    phone_local: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    privacy_policy_accepted: bool = False
    created_at: str

    class Config:
        from_attributes = True


class AdminUserListResponse(BaseModel):
    """Список пользователей для админки (пагинация как у заказов/каталога)."""
    items: list[UserListResponse]
    total: int
    has_more: bool


class UserDetailResponse(UserListResponse):
    pass


def _user_list_row(user: User) -> UserListResponse:
    return UserListResponse(
        id=user.id,
        tgid=user.tgid,
        firstname=user.firstname,
        username=user.username,
        country_code=user.country_code,
        phone_local=user.phone_local,
        email=user.email,
        gender=user.gender,
        privacy_policy_accepted=user.privacy_policy_accepted,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.get("/admin/users", response_model=AdminUserListResponse)
async def list_users(
    _payload: dict = Depends(require_jwt_permission("users")),
    session: AsyncSession = Depends(get_session),
    q: Optional[str] = Query(
        None,
        description="Поиск: внутренний id, TG id, username или имя (подстрока без учёта регистра)",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Получить пользователей с пагинацией; при q — фильтр как в поиске."""
    q_strip = (q or "").strip()
    base = select(User)
    count_stmt = select(func.count()).select_from(User)
    if q_strip:
        try:
            search_id = int(q_strip)
            max_int = 2147483647
            if search_id <= max_int:
                cond = or_(User.id == search_id, User.tgid == search_id)
            else:
                cond = User.tgid == search_id
            base = base.where(cond)
            count_stmt = count_stmt.where(cond)
        except ValueError:
            pattern = f"%{q_strip}%"
            cond = or_(User.username.ilike(pattern), User.firstname.ilike(pattern))
            base = base.where(cond)
            count_stmt = count_stmt.where(cond)

    total = int((await session.execute(count_stmt)).scalar() or 0)
    result = await session.execute(base.order_by(User.id.desc()).offset(skip).limit(limit))
    users = result.scalars().all()
    rows = [_user_list_row(u) for u in users]
    loaded = len(rows)
    return AdminUserListResponse(
        items=rows,
        total=total,
        has_more=(skip + loaded) < total,
    )


# ВАЖНО: Маршрут /admin/users/search должен быть ДО /admin/users/{user_id}
# чтобы FastAPI не интерпретировал "search" как user_id
@router.get("/admin/users/search")
async def search_users(
    q: str = Query(..., min_length=1, description="Внутренний ID, TG ID, username или имя (firstname)"),
    _payload: dict = Depends(require_jwt_permission("users")),
    session: AsyncSession = Depends(get_session)
):
    """Поиск пользователей по id, tgid, username или firstname (без учёта регистра)."""
    q_strip = (q or "").strip()
    if len(q_strip) < 1:
        return []
    try:
        search_id = int(q_strip)
        MAX_INTEGER = 2147483647
        conditions = []
        if search_id <= MAX_INTEGER:
            conditions.append(User.id == search_id)
        conditions.append(User.tgid == search_id)
        result = await session.execute(
            select(User).where(or_(*conditions)).limit(20)
        )
        users = result.scalars().all()
    except ValueError:
        pattern = f"%{q_strip}%"
        result = await session.execute(
            select(User)
            .where(
                or_(
                    User.username.ilike(pattern),
                    User.firstname.ilike(pattern),
                )
            )
            .limit(20)
        )
        users = result.scalars().all()
    return [
        {
            "id": user.id,
            "tgid": user.tgid,
            "firstname": user.firstname,
            "username": user.username,
            "country_code": user.country_code,
            "phone_local": user.phone_local,
            "email": user.email,
            "gender": user.gender,
        }
        for user in users
    ]


@router.get("/admin/users/{user_id}", response_model=UserDetailResponse)
async def get_user_by_id(
    user_id: int,
    _payload: dict = Depends(require_jwt_permission("users")),
    session: AsyncSession = Depends(get_session)
):
    
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    return UserDetailResponse(
        id=user.id,
        tgid=user.tgid,
        firstname=user.firstname,
        username=user.username,
        country_code=user.country_code,
        phone_local=user.phone_local,
        email=user.email,
        gender=user.gender,
        privacy_policy_accepted=user.privacy_policy_accepted,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


async def _call_delete_user_data(service_name: str, base_url: str, user_id: int) -> dict:
    """Вызвать внутренний эндпоинт удаления данных пользователя в сервисе. При ошибке логируем и возвращаем пустой dict."""
    url = f"{base_url.rstrip('/')}/internal/users/{user_id}/delete-all-data"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.delete(url, headers={"X-Internal-Token": INTERNAL_TOKEN})
            if r.status_code == 200:
                return r.json()
            logger.warning("%s: delete-all-data для user_id=%s вернул %s: %s", service_name, user_id, r.status_code, r.text)
    except Exception as e:
        logger.warning("%s: не удалось вызвать delete-all-data для user_id=%s: %s", service_name, user_id, e)
    return {}


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    _payload: dict = Depends(require_jwt_permission("users")),
    session: AsyncSession = Depends(get_session)
):
    """Удалить пользователя (только для owner/admin). Сначала удаляются все связанные данные в других сервисах."""
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Порядок: finance (платежи) → products (заказы, корзина, лайки, отзывы, резервы) → delivery → support
    await _call_delete_user_data("finance", FINANCE_SERVICE_URL, user_id)
    await _call_delete_user_data("products", PRODUCTS_SERVICE_URL, user_id)
    await _call_delete_user_data("delivery", DELIVERY_SERVICE_URL, user_id)
    await _call_delete_user_data("support", SUPPORT_SERVICE_URL, user_id)
    
    # Удаляем запись админа, если пользователь был админом
    admin_result = await session.execute(select(Admin).where(Admin.user_id == user_id))
    admin_record = admin_result.scalar_one_or_none()
    if admin_record:
        await bump_admin_jwt_rev(user_id)
        await session.delete(admin_record)
        await session.commit()
    
    await session.delete(user)
    await session.commit()
    
    return {"message": "Пользователь удален", "user_id": user_id}


# ========== Роли админки (набор прав) ==========

class AdminRoleListItem(BaseModel):
    id: int
    name: str
    permissions: dict


class CreateAdminRoleRequest(BaseModel):
    name: str
    permissions: dict


class UpdateAdminRoleRequest(BaseModel):
    name: Optional[str] = None
    permissions: Optional[dict] = None


@router.get("/admin/roles", response_model=list[AdminRoleListItem])
async def list_admin_roles(
    _: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(AdminRole).order_by(AdminRole.name))
    rows = result.scalars().all()
    return [
        AdminRoleListItem(
            id=r.id,
            name=r.name,
            permissions=parse_permissions_json(r.permissions_json),
        )
        for r in rows
    ]


@router.post("/admin/roles", response_model=AdminRoleListItem)
async def create_admin_role(
    request: CreateAdminRoleRequest,
    _: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    name = (request.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название роли")
    exists = await session.execute(select(AdminRole).where(AdminRole.name == name))
    if exists.scalars().first():
        raise HTTPException(status_code=400, detail="Роль с таким названием уже есть")
    perms = normalize_permissions_payload(request.permissions)
    row = AdminRole(name=name, permissions_json=json.dumps(perms, ensure_ascii=False))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return AdminRoleListItem(
        id=row.id, name=row.name, permissions=parse_permissions_json(row.permissions_json)
    )


@router.get("/admin/roles/{role_id}", response_model=AdminRoleListItem)
async def get_admin_role(
    role_id: int,
    _: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(AdminRole, role_id)
    if not row:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    return AdminRoleListItem(
        id=row.id, name=row.name, permissions=parse_permissions_json(row.permissions_json)
    )


@router.put("/admin/roles/{role_id}", response_model=AdminRoleListItem)
async def update_admin_role(
    role_id: int,
    request: UpdateAdminRoleRequest,
    _: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(AdminRole, role_id)
    if not row:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    if request.name is not None:
        name = (request.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Название не может быть пустым")
        dup = await session.execute(
            select(AdminRole).where(AdminRole.name == name, AdminRole.id != role_id)
        )
        if dup.scalars().first():
            raise HTTPException(status_code=400, detail="Роль с таким названием уже есть")
        row.name = name
    if request.permissions is not None:
        perms = normalize_permissions_payload(request.permissions)
        row.permissions_json = json.dumps(perms, ensure_ascii=False)
    await session.commit()
    await session.refresh(row)
    uid_rows = await session.execute(select(Admin.user_id).where(Admin.role_id == role_id))
    await bump_admin_jwt_rev_many([r[0] for r in uid_rows.all()])
    return AdminRoleListItem(
        id=row.id, name=row.name, permissions=parse_permissions_json(row.permissions_json)
    )


@router.delete("/admin/roles/{role_id}")
async def delete_admin_role(
    role_id: int,
    _: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(AdminRole, role_id)
    if not row:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    cnt = await session.scalar(select(func.count()).select_from(Admin).where(Admin.role_id == role_id))
    if cnt and cnt > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя удалить роль: ей назначены сотрудники ({cnt})",
        )
    await session.delete(row)
    await session.commit()
    return {"message": "Роль удалена", "role_id": role_id}


# ========== Эндпоинты для работы с администраторами ==========

class AdminListResponse(BaseModel):
    user_id: int
    admin_type: str
    role_id: Optional[int] = None
    role_name: Optional[str] = None
    role_title: Optional[str] = None
    permissions: Optional[dict] = None
    login: Optional[str] = None
    tgid: Optional[int] = None

    class Config:
        from_attributes = True


class AdminDetailResponse(AdminListResponse):
    pass


class CreateAdminRequest(BaseModel):
    user_id: Optional[int] = None
    tgid: Optional[int] = None
    role_id: int
    login: str
    password: str

    @field_validator("password", mode="before")
    @classmethod
    def _decode_password_transport(cls, v):
        if v is None or (isinstance(v, str) and not str(v).strip()):
            raise ValueError("password required")
        out = _decode_optional_base64_password_field(str(v))
        if not out:
            raise ValueError("password required")
        return out


class UpdateAdminRequest(BaseModel):
    role_id: Optional[int] = None
    login: Optional[str] = None
    password: Optional[str] = None

    @field_validator("password", mode="before")
    @classmethod
    def _decode_password_transport_optional(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return _decode_optional_base64_password_field(s)


@router.get("/admin/permission-catalog")
async def admin_permission_catalog(_: Admin = Depends(require_owner)):
    """Список всех прав (тумблеры) — для редактора ролей."""
    return permission_catalog_public()


async def _admin_to_list_response(
    session: AsyncSession, admin_obj: Admin, user: Optional[User]
) -> AdminDetailResponse:
    claims = await _resolve_admin_claims(session, admin_obj)
    role_row = (
        await session.get(AdminRole, admin_obj.role_id) if admin_obj.role_id else None
    )
    return AdminDetailResponse(
        user_id=admin_obj.user_id,
        admin_type=claims["admin_type"],
        role_id=admin_obj.role_id,
        role_name=role_row.name if role_row else None,
        role_title=claims.get("role_title"),
        permissions=claims.get("permissions"),
        login=admin_obj.login,
        tgid=user.tgid if user else None,
    )


@router.get("/admin/admins", response_model=list[AdminListResponse])
async def list_admins(
    admin: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session)
):
    """Получить список всех администраторов (только для owner)"""
    result = await session.execute(select(Admin))
    admins = result.scalars().all()

    admin_list = []
    for admin_obj in admins:
        user_result = await session.execute(
            select(User).where(User.id == admin_obj.user_id)
        )
        user = user_result.scalar_one_or_none()
        admin_list.append(await _admin_to_list_response(session, admin_obj, user))

    return admin_list


# ВАЖНО: Маршрут /admin/admins/search должен быть ДО /admin/admins/{user_id}
# чтобы FastAPI не интерпретировал "search" как user_id
@router.get("/admin/admins/search")
async def search_admins(
    q: str = Query(..., min_length=1, description="Поисковый запрос (ID или TG ID)"),
    admin: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session)
):
    """Поиск администраторов по внутреннему ID или tgid (только для owner)"""
    if len(q) < 1:
        return []
    try:
        search_id = int(q)
        MAX_INTEGER = 2147483647
        conditions = []
        if search_id <= MAX_INTEGER:
            conditions.append(User.id == search_id)
        conditions.append(User.tgid == search_id)
        user_result = await session.execute(
            select(User).where(or_(*conditions))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            return []
        admin_result = await session.execute(
            select(Admin).where(Admin.user_id == user.id)
        )
        admin_obj = admin_result.scalar_one_or_none()
        if not admin_obj:
            return []
        row = await _admin_to_list_response(session, admin_obj, user)
        return [row.model_dump()]
    except ValueError:
        return []


@router.get("/admin/admins/{user_id}", response_model=AdminDetailResponse)
async def get_admin_by_id(
    user_id: int,
    admin: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    """Карточка администратора."""
    result = await session.execute(select(Admin).where(Admin.user_id == user_id))
    admin_obj = result.scalar_one_or_none()
    if not admin_obj:
        raise HTTPException(status_code=404, detail="Администратор не найден")
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    return await _admin_to_list_response(session, admin_obj, user)


@router.post("/admin/admins", response_model=AdminDetailResponse)
async def create_admin(
    request: CreateAdminRequest,
    admin: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session)
):
    """Создать сотрудника с гранулярными правами (только owner). Роль «владелец» задаётся только входом Owner."""
    # Находим пользователя
    user = None
    if request.user_id:
        user_result = await session.execute(
            select(User).where(User.id == request.user_id)
        )
        user = user_result.scalar_one_or_none()
    elif request.tgid:
        user_result = await session.execute(
            select(User).where(User.tgid == request.tgid)
        )
        user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверяем, не является ли уже админом
    admin_result = await session.execute(
        select(Admin).where(Admin.user_id == user.id)
    )
    existing_admin = admin_result.scalar_one_or_none()
    if existing_admin:
        raise HTTPException(status_code=400, detail="Этот пользователь уже является администратором")
    
    # Проверяем, не занят ли логин
    if request.login:
        login_result = await session.execute(
            select(Admin).where(Admin.login == request.login)
        )
        existing_login = login_result.scalar_one_or_none()
        if existing_login:
            raise HTTPException(status_code=400, detail="Логин уже занят")

    role_row = await session.get(AdminRole, request.role_id)
    if not role_row:
        raise HTTPException(status_code=400, detail="Роль не найдена")

    new_admin = Admin(
        user_id=user.id,
        admin_type="staff",
        role_id=role_row.id,
        role_title=None,
        permissions_json=None,
        login=request.login,
        password=get_password_hash(request.password),
    )
    session.add(new_admin)
    await session.commit()
    await session.refresh(new_admin)
    return await _admin_to_list_response(session, new_admin, user)


@router.put("/admin/admins/{user_id}", response_model=AdminDetailResponse)
async def update_admin(
    user_id: int,
    request: UpdateAdminRequest,
    admin: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session)
):
    """Обновить сотрудника (только owner). Запись владельца через API не меняется."""
    result = await session.execute(
        select(Admin).where(Admin.user_id == user_id)
    )
    admin_obj = result.scalar_one_or_none()

    if not admin_obj:
        raise HTTPException(status_code=404, detail="Администратор не найден")

    if (admin_obj.admin_type or "").strip().lower() == "owner":
        raise HTTPException(status_code=403, detail="Запись владельца нельзя менять через админку")

    if request.login is not None and request.login != admin_obj.login:
        login_result = await session.execute(
            select(Admin).where(Admin.login == request.login)
        )
        existing_login = login_result.scalar_one_or_none()
        if existing_login:
            raise HTTPException(status_code=400, detail="Логин уже занят")
        admin_obj.login = request.login or None

    if request.role_id is not None:
        role_row = await session.get(AdminRole, request.role_id)
        if not role_row:
            raise HTTPException(status_code=400, detail="Роль не найдена")
        admin_obj.role_id = role_row.id
        admin_obj.permissions_json = None
        admin_obj.role_title = None

    if request.password:
        admin_obj.password = get_password_hash(request.password)

    await session.commit()
    await session.refresh(admin_obj)
    await bump_admin_jwt_rev(user_id)

    user_result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    return await _admin_to_list_response(session, admin_obj, user)


@router.delete("/admin/admins/{user_id}")
async def delete_admin(
    user_id: int,
    admin: Admin = Depends(require_owner),
    session: AsyncSession = Depends(get_session)
):
    """Удалить сотрудника (нельзя удалить владельца и себя)."""
    if user_id == admin.user_id:
        raise HTTPException(status_code=403, detail="Нельзя удалить самого себя")

    result = await session.execute(
        select(Admin).where(Admin.user_id == user_id)
    )
    admin_obj = result.scalar_one_or_none()

    if not admin_obj:
        raise HTTPException(status_code=404, detail="Администратор не найден")

    if (admin_obj.admin_type or "").strip().lower() == "owner":
        raise HTTPException(status_code=403, detail="Нельзя удалить владельца")

    await bump_admin_jwt_rev(user_id)
    await session.delete(admin_obj)
    await session.commit()
    
    return {"message": "Администратор удален", "user_id": user_id}

