"""
Гранулярные права админки. Владелец (admin_type == owner) всегда имеет полный доступ.
Остальные — staff + JSON прав; старые JWT с admin|moderator|support обрабатываются через LEGACY_*.
"""
from __future__ import annotations

import json
from typing import Any

# StoreKPLite: только реально используемые разделы админки.
ALL_ADMIN_PERMISSION_KEYS: tuple[str, ...] = (
    "users",
    "catalog",
    "orders",
)

PERMISSION_LABELS_RU: dict[str, str] = {
    "users": "Пользователи (просмотр, удаление)",
    "catalog": "Каталог товаров",
    "orders": "Заказы",
}


def owner_permissions_dict() -> dict[str, bool]:
    return {k: True for k in ALL_ADMIN_PERMISSION_KEYS}


# Миграция со старых ролей (до staff + JSON)
_LEGACY_MATRIX: dict[str, dict[str, bool]] = {
    "admin": {
        "users": True,
        "catalog": True,
        "orders": True,
    },
    "moderator": {
        "users": True,
        "catalog": True,
        "orders": True,
    },
    "support": {
        "users": False,
        "catalog": False,
        "orders": False,
    },
}

LEGACY_ROLE_TITLE: dict[str, str] = {
    "admin": "Администратор (миграция)",
    "moderator": "Модератор (миграция)",
    "support": "Поддержка (миграция)",
}


def legacy_defaults_for(old_admin_type: str) -> dict[str, bool]:
    t = (old_admin_type or "").strip().lower()
    base = {k: False for k in ALL_ADMIN_PERMISSION_KEYS}
    extra = _LEGACY_MATRIX.get(t, {})
    base.update(extra)
    return base


def parse_permissions_json(raw: str | None) -> dict[str, bool]:
    if not raw or not str(raw).strip():
        return {k: False for k in ALL_ADMIN_PERMISSION_KEYS}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {k: False for k in ALL_ADMIN_PERMISSION_KEYS}
    if not isinstance(data, dict):
        return {k: False for k in ALL_ADMIN_PERMISSION_KEYS}
    out = {k: bool(data.get(k)) for k in ALL_ADMIN_PERMISSION_KEYS}
    return out


def normalize_permissions_payload(data: Any) -> dict[str, bool]:
    """Из тела запроса (dict) — только известные ключи."""
    if not isinstance(data, dict):
        return {k: False for k in ALL_ADMIN_PERMISSION_KEYS}
    return {k: bool(data.get(k)) for k in ALL_ADMIN_PERMISSION_KEYS}


def has_admin_permission(payload: dict, permission: str) -> bool:
    at = (payload.get("admin_type") or "").strip().lower()
    if at == "owner":
        return True
    if permission not in ALL_ADMIN_PERMISSION_KEYS:
        return False
    perms = payload.get("permissions")
    if isinstance(perms, dict) and permission in perms:
        return bool(perms[permission])
    if at in _LEGACY_MATRIX:
        return bool(_LEGACY_MATRIX[at].get(permission))
    return False


def permission_catalog_public() -> list[dict[str, str]]:
    return [{"key": k, "label": PERMISSION_LABELS_RU.get(k, k)} for k in ALL_ADMIN_PERMISSION_KEYS]
