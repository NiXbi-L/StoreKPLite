"""Фоновые задачи: чтение nginx access.log и снимки онлайна."""
from __future__ import annotations

import asyncio
import logging
import os

from api.users.database.database import async_session_maker
from api.users.models.analytics_traffic import OnlineSnapshot
from api.users.services.nginx_log_ingest import run_nginx_log_ingest_once
from api.users.services.online_presence import count_users_online

logger = logging.getLogger(__name__)


async def online_snapshot_loop() -> None:
    await asyncio.sleep(8)
    interval = int(os.getenv("ONLINE_SNAPSHOT_INTERVAL_SEC", "60"))
    while True:
        try:
            n = await count_users_online()
            async with async_session_maker() as session:
                session.add(OnlineSnapshot(online_count=n))
                await session.commit()
        except Exception:
            logger.exception("online_snapshot_loop")
        await asyncio.sleep(max(15, interval))


async def nginx_access_log_ingest_loop() -> None:
    await asyncio.sleep(20)
    interval = int(os.getenv("NGINX_LOG_INGEST_INTERVAL_SEC", "300"))
    while True:
        try:
            async with async_session_maker() as session:
                res = await run_nginx_log_ingest_once(session)
                if res.get("ok"):
                    logger.info("nginx log ingest: %s", res)
                elif res.get("skipped"):
                    logger.info("nginx log ingest skipped: %s", res.get("reason"))
        except Exception:
            logger.exception("nginx_access_log_ingest_loop")
        await asyncio.sleep(max(60, interval))
