"""
Часовой пояс бизнес-логики: UTC+10 (Владивосток).
Все временные границы (неделя, день) считаются во Владивостоке независимо от расположения сервера.
"""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

# Бизнес-часовой пояс: Владивосток (UTC+10), без перехода на летнее время
VLADIVOSTOK = ZoneInfo("Asia/Vladivostok")


def now_vladivostok() -> datetime:
    """Текущее время во Владивостоке (timezone-aware)."""
    return datetime.now(VLADIVOSTOK)


def get_week_start_vladivostok(at: datetime | None = None) -> datetime:
    """
    Начало текущей недели (понедельник 00:00:00) во Владивостоке.
    Используется для истории цен и любых недельных границ.
    :param at: момент времени (во Владивостоке); если None — берётся now_vladivostok().
    """
    if at is None:
        at = now_vladivostok()
    elif at.tzinfo is None:
        at = at.replace(tzinfo=VLADIVOSTOK)
    else:
        at = at.astimezone(VLADIVOSTOK)
    monday = at.date() - timedelta(days=at.weekday())
    return datetime.combine(monday, time(0, 0, 0), tzinfo=VLADIVOSTOK)


def get_current_4h_bucket_start_vladivostok(at: datetime | None = None) -> datetime:
    """
    Начало текущего 4-часового окна во Владивостоке (00:00, 04:00, 08:00, 12:00, 16:00, 20:00).
    Используется для истории цен: запись за текущий день с усреднением по 4 часа.
    """
    if at is None:
        at = now_vladivostok()
    elif at.tzinfo is None:
        at = at.replace(tzinfo=VLADIVOSTOK)
    else:
        at = at.astimezone(VLADIVOSTOK)
    hour = (at.hour // 4) * 4
    return datetime.combine(at.date(), time(hour, 0, 0), tzinfo=VLADIVOSTOK)
