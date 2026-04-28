"""Опциональный GeoIP (MaxMind GeoLite2). Без файла БД страны не считаем."""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_reader = None
_reader_path: Optional[str] = None


def _get_reader():
    global _reader, _reader_path
    path = (os.getenv("MAXMIND_GEOLITE2_CITY") or os.getenv("MAXMIND_GEOLITE2_COUNTRY") or "").strip()
    if not path:
        return None
    if _reader is not None and _reader_path == path:
        return _reader
    try:
        import geoip2.database
    except ImportError:
        logger.warning("geoip2 не установлен; страны по IP не считаем")
        return None
    try:
        _reader = geoip2.database.Reader(path)
        _reader_path = path
        logger.info("GeoIP: загружен %s", path)
        return _reader
    except Exception as e:
        logger.warning("GeoIP: не удалось открыть %s: %s", path, e)
        _reader = None
        _reader_path = None
        return None


def country_iso_for_ip(ip: str) -> Optional[str]:
    """ISO 3166-1 alpha-2 или None."""
    raw = (ip or "").strip()
    if not raw or raw == "::1" or raw.startswith("127.") or raw.startswith("10.") or raw.startswith("192.168."):
        return None
    if raw.startswith("172."):
        try:
            second = int(raw.split(".")[1])
            if 16 <= second <= 31:
                return None
        except (ValueError, IndexError):
            pass
    r = _get_reader()
    if r is None:
        return None
    try:
        rec = r.city(raw)
        c = rec.country.iso_code
        return c.upper() if c else None
    except Exception:
        return None
