"""FastAPI Depends: проверка JWT + гранулярного права."""
from fastapi import Depends, HTTPException, status

from api.shared.auth import verify_jwt_token
from api.shared.admin_permissions import has_admin_permission


def require_jwt_permission(permission: str):
    """Depends(...) — доступ к эндпоинту при наличии права (владелец всегда ок)."""

    async def _dep(payload: dict = Depends(verify_jwt_token)) -> dict:
        if not has_admin_permission(payload, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав",
            )
        return payload

    return _dep


def require_jwt_any_permission(*permissions: str):
    """Хотя бы одно из прав."""

    async def _dep(payload: dict = Depends(verify_jwt_token)) -> dict:
        if any(has_admin_permission(payload, p) for p in permissions):
            return payload
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав",
        )

    return _dep
