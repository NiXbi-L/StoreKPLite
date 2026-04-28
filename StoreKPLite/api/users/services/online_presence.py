"""Онлайн пользователей миниаппа: Redis sorted set + периодические снимки в БД."""
from __future__ import annotations

import logging
import time
from api.users.utils.auth_tokens import get_redis

logger = logging.getLogger(__name__)

PRESENCE_ZSET = "miniapp:presence:z"
# Последний пинг (unix time) — для метрик «активны за N дней»; обрезаем записи старше TRIM дней.
LAST_SEEN_ZSET = "miniapp:last_seen:z"
_LAST_SEEN_TRIM_DAYS = int(__import__("os").getenv("ONLINE_LAST_SEEN_TRIM_DAYS", "40"))
# Heartbeat раз в 5 мин — считаем «онлайн», если пинг был не старше этого окна (сек)
PRESENCE_MAX_AGE_SEC = int(__import__("os").getenv("ONLINE_PRESENCE_TTL_SEC", "900"))


async def touch_user_online(user_id: int) -> None:
    try:
        r = await get_redis()
        now = time.time()
        uid = str(int(user_id))
        await r.zadd(PRESENCE_ZSET, {uid: now})
        await r.zremrangebyscore(PRESENCE_ZSET, 0, now - PRESENCE_MAX_AGE_SEC)
        await r.zadd(LAST_SEEN_ZSET, {uid: now})
        await r.zremrangebyscore(LAST_SEEN_ZSET, 0, now - _LAST_SEEN_TRIM_DAYS * 86400)
    except Exception as e:
        logger.debug("touch_user_online redis skip: %s", e)


async def count_users_online() -> int:
    try:
        r = await get_redis()
        now = time.time()
        await r.zremrangebyscore(PRESENCE_ZSET, 0, now - PRESENCE_MAX_AGE_SEC)
        return int(await r.zcard(PRESENCE_ZSET))
    except Exception as e:
        logger.debug("count_users_online redis skip: %s", e)
        return 0


async def count_users_active_within_seconds(seconds: int) -> int:
    """Сколько уникальных user_id пинговали /users/me/online за последние `seconds` секунд."""
    if seconds < 1:
        return 0
    try:
        r = await get_redis()
        now = time.time()
        await r.zremrangebyscore(LAST_SEEN_ZSET, 0, now - _LAST_SEEN_TRIM_DAYS * 86400)
        return int(await r.zcount(LAST_SEEN_ZSET, now - float(seconds), "+inf"))
    except Exception as e:
        logger.debug("count_users_active_within_seconds redis skip: %s", e)
        return 0
