"""
Утилиты для работы с внутренними токенами авторизации для ботов
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional
import redis.asyncio as redis
from os import getenv

# Redis для хранения токенов
REDIS_URL = getenv("REDIS_URL", "redis://users-redis:6379/0")
redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Получить клиент Redis"""
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


async def generate_internal_token(user_id: int, platform: str, platform_id: int, ttl_seconds: int = 3600) -> str:
    """
    Сгенерировать внутренний токен для бота
    
    Токен сохраняется в Redis с ключом: internal_token:{token}
    Значение: user_id
    TTL: по умолчанию 1 час (можно увеличить для ботов)
    """
    # Генерируем случайный токен
    token = secrets.token_urlsafe(32)
    
    client = await get_redis()
    # Сохраняем токен -> user_id
    await client.setex(f"internal_token:{token}", ttl_seconds, str(user_id))
    
    # Также сохраняем mapping: platform_id -> user_id в Redis бота
    # Ключ: platform_user_id:{platform}:{platform_id} -> user_id
    await client.setex(
        f"platform_user_id:{platform}:{platform_id}",
        ttl_seconds * 24,  # Храним дольше для быстрого доступа
        str(user_id)
    )
    
    return token


async def verify_internal_token(token: str) -> Optional[int]:
    """Проверить внутренний токен и вернуть user_id"""
    client = await get_redis()
    user_id_str = await client.get(f"internal_token:{token}")
    if user_id_str:
        return int(user_id_str)
    return None


async def get_user_id_by_platform(platform: str, platform_id: int) -> Optional[int]:
    """Получить user_id по platform_id из Redis"""
    client = await get_redis()
    user_id_str = await client.get(f"platform_user_id:{platform}:{platform_id}")
    if user_id_str:
        return int(user_id_str)
    return None


async def cache_user_id_for_platform(user_id: int, platform: str, platform_id: int, ttl_seconds: int = 86400):
    """Закэшировать mapping platform_id -> user_id в Redis"""
    client = await get_redis()
    await client.setex(
        f"platform_user_id:{platform}:{platform_id}",
        ttl_seconds,
        str(user_id)
    )


async def revoke_internal_token(token: str):
    """Отозвать внутренний токен"""
    client = await get_redis()
    await client.delete(f"internal_token:{token}")

