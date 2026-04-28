"""
Утилита для работы с Redis
"""
import redis.asyncio as redis
import json
import logging
from os import getenv
from typing import Optional, Set, List

logger = logging.getLogger(__name__)

REDIS_URL = getenv("REDIS_URL", "redis://redis:6379/0")

# Глобальный клиент Redis
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Получить клиент Redis (singleton)"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info(f"Подключен к Redis: {REDIS_URL}")
    return _redis_client


async def close_redis():
    """Закрыть соединение с Redis"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Соединение с Redis закрыто")


# Ключи для хранения данных
def get_user_feed_key(tgid: int) -> str:
    """Ключ для хранения истории показа товаров пользователю (24 часа)"""
    return f"feed:user:{tgid}:items"


def get_user_disliked_key(tgid: int) -> str:
    """Ключ для хранения дизлайкнутых товаров пользователя (навсегда)"""
    return f"feed:user:{tgid}:disliked"


def get_user_liked_key(tgid: int) -> str:
    """Ключ для хранения лайкнутых товаров пользователя (навсегда)"""
    return f"feed:user:{tgid}:liked"


def get_user_viewed_key(tgid: int) -> str:
    """Ключ для хранения просмотренных товаров пользователя (для повторного показа)"""
    return f"feed:user:{tgid}:viewed"


async def add_to_feed_history(tgid: int, item_id: int):
    """Добавить товар в историю показа (TTL 24 часа)"""
    client = await get_redis()
    key = get_user_feed_key(tgid)
    await client.sadd(key, str(item_id))
    await client.expire(key, 86400)  # 24 часа


async def get_feed_history(tgid: int) -> Set[int]:
    """Получить историю показанных товаров"""
    client = await get_redis()
    key = get_user_feed_key(tgid)
    items = await client.smembers(key)
    return {int(item_id) for item_id in items}


async def add_disliked(tgid: int, item_id: int):
    """Добавить товар в дизлайки (навсегда)"""
    client = await get_redis()
    key = get_user_disliked_key(tgid)
    await client.sadd(key, str(item_id))


async def get_disliked(tgid: int) -> Set[int]:
    """Получить список дизлайкнутых товаров"""
    client = await get_redis()
    key = get_user_disliked_key(tgid)
    items = await client.smembers(key)
    return {int(item_id) for item_id in items}


async def add_liked(tgid: int, item_id: int):
    """Добавить товар в лайки (навсегда)"""
    client = await get_redis()
    key = get_user_liked_key(tgid)
    await client.sadd(key, str(item_id))


async def get_liked(tgid: int) -> Set[int]:
    """Получить список лайкнутых товаров"""
    client = await get_redis()
    key = get_user_liked_key(tgid)
    items = await client.smembers(key)
    return {int(item_id) for item_id in items}


async def add_viewed(tgid: int, item_id: int):
    """Добавить товар в просмотренные (для повторного показа)"""
    client = await get_redis()
    key = get_user_viewed_key(tgid)
    await client.sadd(key, str(item_id))
    # Храним просмотренные 7 дней
    await client.expire(key, 604800)


async def get_viewed(tgid: int) -> Set[int]:
    """Получить список просмотренных товаров"""
    client = await get_redis()
    key = get_user_viewed_key(tgid)
    items = await client.smembers(key)
    return {int(item_id) for item_id in items}


