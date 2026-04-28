"""
Инкрементальное чтение nginx access.log и запись агрегатов в traffic_analytics_daily.
Страны по IP — только для запросов НЕ под /miniapp/ (веб без VPN).
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, DefaultDict, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.users.models.analytics_traffic import NginxLogIngestState, TrafficAnalyticsDaily
from api.users.services.geoip_lookup import country_iso_for_ip

logger = logging.getLogger(__name__)

# Час и календарный день в агрегатах — как на дашборде (онлайн уже в этом поясе).
TRAFFIC_DASHBOARD_TZ = ZoneInfo("Asia/Vladivostok")

# Как в docker-compose по умолчанию; если env не задан — всё равно пробуем стандартный путь в контейнере
DEFAULT_NGINX_ACCESS_LOG = "/var/log/nginx/shared/access.log"


def effective_nginx_access_log_path() -> str:
    p = (os.getenv("NGINX_ACCESS_LOG_PATH") or "").strip()
    return p if p else DEFAULT_NGINX_ACCESS_LOG


# main: '$remote_addr - $remote_user [$time_local] "$request" $status $bytes "$referer" "$ua" "$xff"'
NGINX_LINE_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>\S+)(?: [^"]*)?" (?P<status>\d+) (?P<size>\S+) '
    r'"(?P<ref>[^"]*)" "(?P<ua>[^"]*)"(?: "(?P<xff>[^"]*)")?\s*$'
)

MOBILE_UA_RE = re.compile(
    r"Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/|Mobile\s",
    re.I,
)


def _empty_hourly() -> List[int]:
    return [0] * 24


def _parse_time_local(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    for fmt in ("%d/%b/%Y:%H:%M:%S %z", "%d/%b/%Y:%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _ensure_aware_utc(dt: datetime) -> datetime:
    """
    Nginx $time_local в контейнере обычно UTC (+0000) или наивное время без суффикса (тоже трактуем как UTC).
    Иначе задайте NGINX_ACCESS_LOG_ASSUME_TZ=Area/City для наивной строки.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    assume = (os.getenv("NGINX_ACCESS_LOG_ASSUME_TZ") or "UTC").strip()
    if assume.upper() == "UTC":
        return dt.replace(tzinfo=timezone.utc)
    try:
        zi = ZoneInfo(assume)
    except Exception:
        logger.warning("NGINX_ACCESS_LOG_ASSUME_TZ=%r invalid, using UTC", assume)
        return dt.replace(tzinfo=timezone.utc)
    return dt.replace(tzinfo=zi).astimezone(timezone.utc)


def _traffic_period_date_and_hour(dt: datetime) -> Tuple[date, int]:
    """Дата строки в traffic_analytics_daily и слот 0..23 — по стенным часам Владивостока."""
    local = _ensure_aware_utc(dt).astimezone(TRAFFIC_DASHBOARD_TZ)
    return local.date(), local.hour


def _is_miniapp_path(path: str) -> bool:
    p = path or ""
    return p.startswith("/miniapp") or p.startswith("/miniap/")


def _client_ip(record_ip: str, xff: Optional[str]) -> str:
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return (record_ip or "").strip()


def _classify_web_ua(ua: str) -> str:
    u = ua or ""
    if not u.strip():
        return "unknown"
    if MOBILE_UA_RE.search(u):
        return "mobile"
    return "desktop"


@dataclass
class DayAgg:
    miniapp: int = 0
    web_mobile: int = 0
    web_desktop: int = 0
    web_unknown: int = 0
    hourly: List[int] = field(default_factory=_empty_hourly)
    country_web: Dict[str, int] = field(default_factory=dict)


def _merge_day(dst: DayAgg, src: DayAgg) -> None:
    dst.miniapp += src.miniapp
    dst.web_mobile += src.web_mobile
    dst.web_desktop += src.web_desktop
    dst.web_unknown += src.web_unknown
    for i in range(24):
        dst.hourly[i] += src.hourly[i]
    for k, v in src.country_web.items():
        dst.country_web[k] = dst.country_web.get(k, 0) + v


def _process_line(line: str) -> Optional[Tuple[date, DayAgg]]:
    m = NGINX_LINE_RE.match(line.rstrip("\n"))
    if not m:
        return None
    path = m.group("path")
    ua = m.group("ua") or ""
    dt = _parse_time_local(m.group("time"))
    if dt is None:
        return None
    log_date, hour = _traffic_period_date_and_hour(dt)
    ip = _client_ip(m.group("ip"), m.group("xff"))

    agg = DayAgg()
    agg.hourly[hour] += 1

    if _is_miniapp_path(path):
        agg.miniapp += 1
        return log_date, agg

    w = _classify_web_ua(ua)
    if w == "mobile":
        agg.web_mobile += 1
    elif w == "desktop":
        agg.web_desktop += 1
    else:
        agg.web_unknown += 1

    cc = country_iso_for_ip(ip)
    if cc:
        agg.country_web[cc] = 1
    else:
        agg.country_web["ZZ"] = agg.country_web.get("ZZ", 0) + 1

    return log_date, agg


async def _get_or_create_ingest_state(session: AsyncSession) -> NginxLogIngestState:
    row = await session.get(NginxLogIngestState, 1)
    if row is None:
        row = NginxLogIngestState(id=1, log_path="", byte_offset=0, file_inode=None)
        session.add(row)
        await session.flush()
    return row


async def _merge_traffic_row(
    session: AsyncSession,
    log_date: date,
    delta: DayAgg,
) -> None:
    result = await session.execute(select(TrafficAnalyticsDaily).where(TrafficAnalyticsDaily.period_date == log_date))
    row = result.scalar_one_or_none()
    if row is None:
        row = TrafficAnalyticsDaily(
            period_date=log_date,
            miniapp_requests=0,
            web_mobile_requests=0,
            web_desktop_requests=0,
            web_unknown_requests=0,
            hourly_total_json=json.dumps(_empty_hourly()),
            country_web_json=json.dumps({}),
        )
        session.add(row)
        await session.flush()

    h = json.loads(row.hourly_total_json or "[]")
    if len(h) != 24:
        h = _empty_hourly()
    for i in range(24):
        h[i] += delta.hourly[i]

    c = json.loads(row.country_web_json or "{}")
    if not isinstance(c, dict):
        c = {}
    for k, v in delta.country_web.items():
        c[k] = int(c.get(k, 0)) + int(v)

    row.miniapp_requests = int(row.miniapp_requests or 0) + delta.miniapp
    row.web_mobile_requests = int(row.web_mobile_requests or 0) + delta.web_mobile
    row.web_desktop_requests = int(row.web_desktop_requests or 0) + delta.web_desktop
    row.web_unknown_requests = int(row.web_unknown_requests or 0) + delta.web_unknown
    row.hourly_total_json = json.dumps(h)
    row.country_web_json = json.dumps(c)


async def run_nginx_log_ingest_once(session: AsyncSession) -> Dict[str, Any]:
    log_path = effective_nginx_access_log_path()

    if not os.path.isfile(log_path):
        return {"ok": False, "skipped": True, "reason": f"file missing: {log_path}"}

    st = os.stat(log_path)
    state = await _get_or_create_ingest_state(session)
    offset = int(state.byte_offset or 0)

    if state.file_inode is not None and st.st_ino != int(state.file_inode):
        logger.info("nginx log rotated (inode changed), offset reset")
        offset = 0
    if offset > st.st_size:
        offset = 0

    state.log_path = log_path[:1024]
    state.file_inode = int(st.st_ino)

    by_day: DefaultDict[date, DayAgg] = defaultdict(DayAgg)
    lines = 0
    parsed_ok = 0

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            for line in f:
                lines += 1
                parsed = _process_line(line)
                if not parsed:
                    continue
                parsed_ok += 1
                d, agg = parsed
                _merge_day(by_day[d], agg)
            new_offset = f.tell()
    except Exception as e:
        state.last_error = str(e)[:2000]
        await session.commit()
        logger.exception("nginx log ingest read error")
        return {"ok": False, "error": str(e)}

    if lines >= 50 and parsed_ok == 0:
        logger.warning(
            "nginx access.log: прочитано %s строк, ни одна не совпала с форматом main "
            "(remote user time request status … referer ua xff). Проверьте log_format в nginx.",
            lines,
        )

    for d, agg in sorted(by_day.items()):
        await _merge_traffic_row(session, d, agg)

    state.byte_offset = new_offset
    state.last_run_at = datetime.now(timezone.utc)
    state.last_error = None
    state.lines_processed_total = int(state.lines_processed_total or 0) + lines
    await session.commit()

    return {
        "ok": True,
        "lines": lines,
        "parsed": parsed_ok,
        "days_touched": len(by_day),
        "new_offset": new_offset,
    }


async def fetch_traffic_summary_for_dashboard(session: AsyncSession) -> Dict[str, Any]:
    result = await session.execute(
        select(TrafficAnalyticsDaily).order_by(TrafficAnalyticsDaily.period_date.desc()).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return {
            "has_data": False,
            "period_date": None,
            "percent": {},
            "country_web_percent": {},
            "hourly_total": _empty_hourly(),
        }

    m = int(row.miniapp_requests or 0)
    wm = int(row.web_mobile_requests or 0)
    wd = int(row.web_desktop_requests or 0)
    wu = int(row.web_unknown_requests or 0)
    total = m + wm + wd + wu
    if total <= 0:
        pct: Dict[str, float] = {}
    else:
        pct = {
            "miniapp": round(100.0 * m / total, 2),
            "web_mobile": round(100.0 * wm / total, 2),
            "web_desktop": round(100.0 * wd / total, 2),
            "web_unknown": round(100.0 * wu / total, 2),
        }

    cts = json.loads(row.country_web_json or "{}")
    if not isinstance(cts, dict):
        cts = {}
    csum = sum(int(v) for v in cts.values())
    country_pct: Dict[str, float] = {}
    if csum > 0:
        for k, v in sorted(cts.items(), key=lambda x: -int(x[1]))[:40]:
            country_pct[str(k)] = round(100.0 * int(v) / csum, 2)

    hourly = json.loads(row.hourly_total_json or "[]")
    if not isinstance(hourly, list) or len(hourly) != 24:
        hourly = _empty_hourly()
    else:
        hourly = [int(x) for x in hourly]

    return {
        "has_data": True,
        "period_date": row.period_date.isoformat() if row.period_date else None,
        "counts": {"miniapp": m, "web_mobile": wm, "web_desktop": wd, "web_unknown": wu, "total": total},
        "percent": pct,
        "country_web_percent": country_pct,
        "hourly_total": hourly,
    }


async def fetch_ingest_meta(session: AsyncSession) -> Dict[str, Any]:
    state = await session.get(NginxLogIngestState, 1)
    if state is None:
        return {
            "log_path": effective_nginx_access_log_path(),
            "byte_offset": 0,
            "last_run_at": None,
            "last_error": None,
        }
    return {
        "log_path": state.log_path,
        "byte_offset": int(state.byte_offset or 0),
        "last_run_at": state.last_run_at.isoformat() if state.last_run_at else None,
        "last_error": state.last_error,
        "lines_total": int(state.lines_processed_total or 0),
    }
