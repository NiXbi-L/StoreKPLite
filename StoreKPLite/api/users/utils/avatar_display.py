"""Какой URL аватара отдавать наружу: свой загруз, иначе фото из Telegram."""

from __future__ import annotations

from typing import Any, Optional


def _normalize_https(url: Optional[str]) -> Optional[str]:
    if not url or not str(url).strip():
        return None
    u = str(url).strip()
    if u.lower().startswith("http://"):
        return "https://" + u[7:]
    return u


def effective_avatar_url(user: Any) -> Optional[str]:
    """Приоритет: profile_avatar_url, затем telegram_photo_url."""
    p = getattr(user, "profile_avatar_url", None)
    if p and str(p).strip():
        return _normalize_https(p)
    t = getattr(user, "telegram_photo_url", None)
    if t and str(t).strip():
        return _normalize_https(t)
    return None
