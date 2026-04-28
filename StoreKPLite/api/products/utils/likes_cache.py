"""Кеш и ревизии списков лайков (products-redis, REDIS_URL)."""

from __future__ import annotations

import json
import logging
from os import getenv
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

REDIS_URL = getenv("REDIS_URL", "redis://products-redis:6379/0")
TTL_IDS = 86400
TTL_SUMMARY = 86400


def _rev_key(platform: str, user_id: int, action: str) -> str:
    return f"likes:rev:{platform}:{user_id}:{action}"


def _ids_key(platform: str, user_id: int, action: str, rev: int) -> str:
    return f"likes:ids:{platform}:{user_id}:{action}:{rev}"


def _summary_key(platform: str, user_id: int, action: str, rev: int) -> str:
    return f"likes:summary:{platform}:{user_id}:{action}:{rev}"


async def bump_likes_revisions(platform: str, user_id: int, actions: Iterable[str]) -> None:
    """Инкремент ревизии для затронутых полок (like / dislike / save) — сбрасывает кеш списка и summary."""
    try:
        import redis.asyncio as redis

        client = await redis.from_url(REDIS_URL, decode_responses=True)
        for a in {str(x).strip().lower() for x in actions if x}:
            if a in ("like", "dislike", "save"):
                await client.incr(_rev_key(platform, user_id, a))
        await client.close()
    except Exception as exc:
        logger.debug("likes_cache bump skip: %s", exc)


async def get_likes_revision(platform: str, user_id: int, action: str) -> int:
    try:
        import redis.asyncio as redis

        client = await redis.from_url(REDIS_URL, decode_responses=True)
        raw = await client.get(_rev_key(platform, user_id, action))
        await client.close()
        if raw is None or raw == "":
            return 0
        return int(raw)
    except Exception:
        return 0


async def get_cached_summary_total(platform: str, user_id: int, action: str, rev: int) -> Optional[int]:
    try:
        import redis.asyncio as redis

        client = await redis.from_url(REDIS_URL, decode_responses=True)
        raw = await client.get(_summary_key(platform, user_id, action, rev))
        await client.close()
        if raw is None or raw == "":
            return None
        return int(raw)
    except Exception:
        return None


async def set_cached_summary_total(platform: str, user_id: int, action: str, rev: int, total: int) -> None:
    try:
        import redis.asyncio as redis

        client = await redis.from_url(REDIS_URL, decode_responses=True)
        await client.setex(_summary_key(platform, user_id, action, rev), TTL_SUMMARY, str(int(total)))
        await client.close()
    except Exception as exc:
        logger.debug("likes_cache set summary skip: %s", exc)


async def get_cached_like_item_ids(platform: str, user_id: int, action: str, rev: int) -> Optional[List[int]]:
    try:
        import redis.asyncio as redis

        client = await redis.from_url(REDIS_URL, decode_responses=True)
        raw = await client.get(_ids_key(platform, user_id, action, rev))
        await client.close()
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, list):
            return None
        return [int(x) for x in data]
    except Exception:
        return None


async def set_cached_like_item_ids(platform: str, user_id: int, action: str, rev: int, item_ids: List[int]) -> None:
    try:
        import redis.asyncio as redis

        client = await redis.from_url(REDIS_URL, decode_responses=True)
        await client.setex(_ids_key(platform, user_id, action, rev), TTL_IDS, json.dumps(item_ids))
        await client.close()
    except Exception as exc:
        logger.debug("likes_cache set ids skip: %s", exc)
