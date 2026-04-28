"""Список Origin для CORS.

Приоритет:
1) CORS_ALLOWED_ORIGINS — явный список через запятую;
2) иначе origin из API_BASE_URL (scheme + host, без path);
3) иначе пустой список (задайте переменные окружения).
"""
from os import getenv
from urllib.parse import urlparse


def _origin_from_api_base_url() -> str | None:
    base = getenv("API_BASE_URL", "").strip().rstrip("/")
    if not base:
        return None
    if "://" not in base:
        base = f"https://{base}"
    p = urlparse(base)
    if not p.scheme or not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc}"


def cors_allowed_origins() -> list[str]:
    raw = getenv("CORS_ALLOWED_ORIGINS")
    if raw is not None and raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    origin = _origin_from_api_base_url()
    if origin:
        return [origin]
    return []
