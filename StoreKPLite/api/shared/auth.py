"""
Общие утилиты авторизации для микросервисов
"""
from typing import Optional
import asyncio
import logging
import time
from fastapi import HTTPException, Security, Header, status, Cookie, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from os import getenv
import httpx

from api.shared.admin_jwt_rev import (
    ensure_admin_sid_is_active,
    is_admin_portal_jwt_payload,
)

logger = logging.getLogger(__name__)

# Ответ при режиме «миниапп только для админов» (JWT миниаппа без admin_type)
MINIAPP_ADMIN_ONLY_DETAIL = {
    "code": "MINIAPP_ADMIN_ONLY",
    "message": "Мини-приложение временно доступно только администраторам.",
}

_miniapp_only_ts = 0.0
_miniapp_only_val = False
_miniapp_only_lock = asyncio.Lock()
MINIAPP_ONLY_TTL_SEC = 2.5


async def fetch_miniapp_admin_only_flag() -> bool:
    base = USERS_SERVICE_URL.rstrip("/")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base}/public/miniapp-mode", timeout=2.5)
        if r.status_code != 200:
            return False
        return bool(r.json().get("admin_only"))
    except Exception:
        return False


def bump_miniapp_admin_only_cache() -> None:
    """Сбросить кэш флага (после смены настроек в users-service)."""
    global _miniapp_only_ts
    _miniapp_only_ts = 0.0


async def is_miniapp_admin_only_mode() -> bool:
    """
    Флаг с users-service (кэш). При ошибке сети — False, чтобы не отрезать трафик из‑за сбоя.
    """
    global _miniapp_only_ts, _miniapp_only_val
    now = time.monotonic()
    if now - _miniapp_only_ts < MINIAPP_ONLY_TTL_SEC:
        return _miniapp_only_val
    async with _miniapp_only_lock:
        now = time.monotonic()
        if now - _miniapp_only_ts < MINIAPP_ONLY_TTL_SEC:
            return _miniapp_only_val
        val = await fetch_miniapp_admin_only_flag()
        _miniapp_only_ts = time.monotonic()
        _miniapp_only_val = val
        return val


async def enforce_miniapp_access_for_jwt_payload(payload: dict) -> None:
    """JWT админки (есть login) и любой JWT с непустым admin_type — без ограничения."""
    if is_admin_portal_jwt_payload(payload):
        return
    at = payload.get("admin_type")
    if at is not None and str(at).strip():
        return
    if await is_miniapp_admin_only_mode():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MINIAPP_ADMIN_ONLY_DETAIL,
        )

# JWT настройки для админского доступа
_DEFAULT_JWT_SECRET = "your-secret-key-change-in-production"
SECRET_KEY = getenv("JWT_SECRET_KEY", _DEFAULT_JWT_SECRET)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 часа
REFRESH_TOKEN_EXPIRE_DAYS = 30

if SECRET_KEY == _DEFAULT_JWT_SECRET:
    allow_insecure = getenv("JWT_ALLOW_INSECURE_DEFAULT", "false").lower() in {"1", "true", "yes"}
    if not allow_insecure:
        raise RuntimeError(
            "JWT_SECRET_KEY не задан. Запуск с дефолтным секретом запрещён; "
            "для локальной отладки установите JWT_ALLOW_INSECURE_DEFAULT=true."
        )
    logger.warning(
        "JWT_SECRET_KEY не задан — используется значение по умолчанию. "
        "В проде обязательно задайте JWT_SECRET_KEY в окружении."
    )

# URL сервиса пользователей для проверки внутренних токенов
USERS_SERVICE_URL = getenv("USERS_SERVICE_URL", "http://users-service:8001")

security = HTTPBearer(auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создать JWT токен для админского доступа"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создать refresh JWT токен (для админ-портала)."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def verify_jwt_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    authorization: Optional[str] = Header(None),
    admin_access_token: Optional[str] = Cookie(None, alias="admin_access_token"),
) -> dict:
    """Проверить JWT токен и вернуть данные пользователя (Bearer, заголовок Authorization или cookie admin_access_token)."""
    try:
        token: Optional[str] = None
        if credentials is not None and credentials.credentials:
            token = credentials.credentials
        elif authorization and authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "")
        elif admin_access_token:
            token = admin_access_token.strip() or None
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Требуется токен авторизации",
                headers={"WWW-Authenticate": "Bearer"},
            )
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        admin_type: str = payload.get("admin_type")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Невалидный токен",
                headers={"WWW-Authenticate": "Bearer"},
            )
        await ensure_admin_sid_is_active(payload)
        await enforce_miniapp_access_for_jwt_payload(payload)
        sid_raw = payload.get("sid")
        sid = str(sid_raw).strip() if sid_raw is not None else ""
        data = {
            "user_id": int(user_id),
            "admin_type": admin_type,
            "login": payload.get("login"),
            "permissions": payload.get("permissions"),
            "role_title": payload.get("role_title"),
            "sid": sid or None,
        }
        return data
    except HTTPException:
        raise
    except (JWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_internal_user_id(
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    platform_id: Optional[str] = Header(None, alias="X-Platform-Id"),
    platform: Optional[str] = Header(None, alias="X-Platform"),
) -> int:
    """
    Получить внутренний ID пользователя из внутреннего токена бота
    
    Боты передают внутренний токен, который был выдан сервисом users.
    Сервис проверяет токен через HTTP запрос к users service.
    """
    if not x_internal_token or not platform_id or not platform:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется внутренний токен и данные платформы",
        )
    
    # Проверяем токен через сервис users
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{USERS_SERVICE_URL}/auth/verify-internal",
                headers={
                    "X-Internal-Token": x_internal_token,
                    "X-Platform-Id": platform_id,
                    "X-Platform": platform,
                },
                timeout=5.0
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Невалидный внутренний токен",
                )
            data = response.json()
            return data["user_id"]
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис авторизации недоступен",
        )


async def get_user_id_for_request(
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    platform_id: Optional[str] = Header(None, alias="X-Platform-Id"),
    platform: Optional[str] = Header(None, alias="X-Platform"),
) -> int:
    """
    Универсальная функция для получения user_id

    Поддерживает два типа авторизации:
    1. JWT токен (для админов/внешних приложений) - заголовок Authorization
    2. Внутренний токен (для ботов) - заголовки X-Internal-Token, X-Platform-Id, X-Platform

    Приоритет: JWT токен, если есть, иначе внутренний токен
    """
    if authorization and authorization.startswith("Bearer "):
        try:
            token = authorization.replace("Bearer ", "")
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            await ensure_admin_sid_is_active(payload)
            await enforce_miniapp_access_for_jwt_payload(payload)
            user_id = payload.get("sub")
            if user_id:
                return int(user_id)
        except HTTPException:
            raise
        except (JWTError, ValueError, KeyError):
            pass
    return await get_internal_user_id(x_internal_token, platform_id, platform)


async def decode_access_token_admin_type_optional(token: str) -> Optional[str]:
    """
    Для валидного access JWT (миниапп/админка) вернуть admin_type в нижнем регистре или None.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        await ensure_admin_sid_is_active(payload)
        await enforce_miniapp_access_for_jwt_payload(payload)
        at = payload.get("admin_type")
        if at is None:
            return None
        s = str(at).strip().lower()
        return s if s else None
    except HTTPException:
        raise
    except (JWTError, ValueError, KeyError, TypeError):
        return None


async def get_bearer_jwt_admin_type_optional(
    authorization: Optional[str] = Header(None),
) -> Optional[str]:
    """
    Для валидного Bearer JWT миниаппа вернуть admin_type в нижнем регистре (например «owner»).
    Если заголовка нет или токен не JWT / невалиден — None (без 401: совместимо с внутренним токеном бота).
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        return None
    return await decode_access_token_admin_type_optional(token)


async def get_jwt_admin_type_optional_from_request(
    request: Request,
    authorization: Optional[str] = None,
) -> Optional[str]:
    """
    admin_type из Bearer или cookie admin_access_token (чекаут / оплата с админки под cookie).
    """
    token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip() or None
    if not token:
        token = (request.cookies.get("admin_access_token") or "").strip() or None
    if not token:
        return None
    return await decode_access_token_admin_type_optional(token)


async def _fetch_phone_from_users_service(user_id: int) -> Optional[str]:
    """Запросить актуальный phone_local у users service (если в JWT его нет или он устарел)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{USERS_SERVICE_URL}/users/{user_id}",
                timeout=5.0,
            )
            if response.status_code != 200:
                return None
            data = response.json()
            phone = data.get("phone_local")
            phone_str = (phone or "").strip() if phone is not None else ""
            return phone_str if phone_str else None
    except Exception:
        return None


async def get_profile_phone(user_id: int) -> Optional[str]:
    """Получить номер телефона из профиля пользователя (запрос к users service)."""
    return await _fetch_phone_from_users_service(user_id)


async def get_user_id_and_profile_phone(
    authorization: Optional[str] = Header(None),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
    platform_id: Optional[str] = Header(None, alias="X-Platform-Id"),
    platform: Optional[str] = Header(None, alias="X-Platform"),
) -> tuple[int, Optional[str]]:
    """
    Возвращает (user_id, profile_phone_local).
    Если в JWT нет phone_local (токен выдан до добавления номера), запрашиваются актуальные
    данные у users service. Если и там номера нет — возвращается (user_id, None); вызывающий
    код должен вернуть отказ (например 403) с просьбой добавить номер в профиль.
    """
    if authorization and authorization.startswith("Bearer "):
        try:
            token = authorization.replace("Bearer ", "")
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            await ensure_admin_sid_is_active(payload)
            await enforce_miniapp_access_for_jwt_payload(payload)
            user_id = payload.get("sub")
            if user_id:
                user_id = int(user_id)
                phone = payload.get("phone_local")
                phone_str = (phone or "").strip() if phone is not None else ""
                if phone_str:
                    return user_id, phone_str
                # В JWT нет номера — запрашиваем актуальный профиль у users service
                profile_phone = await _fetch_phone_from_users_service(user_id)
                return user_id, profile_phone
        except HTTPException:
            raise
        except (JWTError, ValueError, KeyError):
            pass
    user_id = await get_internal_user_id(x_internal_token, platform_id, platform)
    # Для внутреннего токена (бот) тоже запрашиваем телефон из users service
    profile_phone = await _fetch_phone_from_users_service(user_id)
    return user_id, profile_phone


def require_admin_type(required_type: str = "admin"):
    """Декоратор для проверки типа админа"""
    async def check_admin(
        credentials: HTTPAuthorizationCredentials = Security(security)
    ) -> dict:
        user_data = await verify_jwt_token(credentials)
        admin_type = user_data.get("admin_type")
        
        admin_hierarchy = {
            "owner": 4,
            "admin": 3,
            "moderator": 2,
            "support": 1
        }
        
        user_level = admin_hierarchy.get(admin_type, 0)
        required_level = admin_hierarchy.get(required_type, 0)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Требуется уровень доступа: {required_type}"
            )
        
        return user_data
    
    return check_admin
