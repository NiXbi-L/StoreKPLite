"""
Клиент к внешнему сервису bot_api_service (bridge) и при необходимости — к Telegram.

Канон для продакшена (РФ): микросервисы не ходят в api.telegram.org сами, а POSTят на
  {API_BASE_URL}/bot-api/internal/...
Nginx проксирует /bot-api/ на инстанс **bot_api_service** (часто за пределами РФ, где TG не блокируют);
сам bridge держит BOT_TOKEN и вызывает https://api.telegram.org/...

Локально / без nginx: SKIP_TELEGRAM_HTTP_BRIDGE=1 или пустой API_BASE_URL → прямой api.telegram.org при BOT_TOKEN.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_DIRECT = "https://api.telegram.org/bot"
# Публичный path на том же origin, что API_BASE_URL; nginx сматчивает и шлёт на BOT_API_URL upstream.
_DEFAULT_BOT_HTTP_PREFIX = "/bot-api"


def _internal_headers() -> Dict[str, str]:
    token = (os.getenv("INTERNAL_TOKEN") or "").strip() or "internal-secret-token-change-in-production"
    return {"X-Internal-Token": token}


def bot_api_base() -> Optional[str]:
    if (os.getenv("SKIP_TELEGRAM_HTTP_BRIDGE") or "").strip().lower() in ("1", "true", "yes"):
        return None
    api_base = (os.getenv("API_BASE_URL") or "").strip().rstrip("/")
    if not api_base:
        return None
    return f"{api_base}{_DEFAULT_BOT_HTTP_PREFIX}"


def bot_token() -> Optional[str]:
    t = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    return t or None


def _use_bridge() -> bool:
    return bool(bot_api_base())


async def _post_telegram_direct(subpath: str, **kwargs: Any) -> httpx.Response:
    token = bot_token()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан для прямого вызова Telegram")
    url = f"{TELEGRAM_DIRECT}{token}/{subpath}"
    async with httpx.AsyncClient() as client:
        return await client.post(url, **kwargs)


async def _get_telegram_direct(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    token = bot_token()
    if not token:
        return {"ok": False, "description": "BOT_TOKEN не задан"}
    url = f"{TELEGRAM_DIRECT}{token}/{method}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params, timeout=20.0)
        try:
            return r.json()
        except Exception:
            return {"ok": False, "description": r.text[:300]}


async def telegram_send_message_with_result(
    chat_id: Union[int, str],
    text: str,
    *,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[dict] = None,
    timeout: float = 10.0,
) -> Tuple[bool, Optional[str]]:
    """
    Отправка sendMessage через bot_api_service (если задан API_BASE_URL → …/bot-api) или прямой Telegram.
    Возвращает (успех, текст_ошибки). Учитывает JSON Telegram: при HTTP 200 и ok=false — неуспех.
    """
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    base = bot_api_base()
    try:
        if base:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{base}/internal/send-message",
                    json=payload,
                    headers=_internal_headers(),
                )
                if r.status_code != 200:
                    return False, (r.text or "")[:500]
                try:
                    body = r.json()
                except Exception:
                    return False, (r.text or "")[:500]
                if not body.get("ok"):
                    return False, str(body.get("description") or body)[:500]
                return True, None
        r = await _post_telegram_direct("sendMessage", json=payload, timeout=timeout)
        if r.status_code != 200:
            return False, (r.text or "")[:500]
        try:
            body = r.json()
        except Exception:
            return False, (r.text or "")[:500]
        if not body.get("ok"):
            return False, str(body.get("description") or body)[:500]
        return True, None
    except Exception as e:
        return False, str(e)[:500]


async def telegram_send_message(
    chat_id: Union[int, str],
    text: str,
    *,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[dict] = None,
    timeout: float = 10.0,
) -> None:
    ok, err = await telegram_send_message_with_result(
        chat_id,
        text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
        timeout=timeout,
    )
    if ok:
        logger.info("Сообщение Telegram отправлено в chat_id=%s", chat_id)
    elif err:
        logger.error("Ошибка отправки в Telegram chat_id=%s: %s", chat_id, err)
    else:
        logger.error("Ошибка отправки в Telegram chat_id=%s (без описания)", chat_id)


async def telegram_send_photo_multipart(
    chat_id: Union[int, str],
    photo_filename: str,
    photo_bytes: bytes,
    content_type: str,
    *,
    caption: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    sendPhoto (файл). Возвращает JSON ответа Telegram (dict).
    """
    files = {"photo": (photo_filename, photo_bytes, content_type or "image/jpeg")}
    data: Dict[str, str] = {"chat_id": str(chat_id)}
    if caption is not None:
        data["caption"] = caption
    base = bot_api_base()
    if base:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{base}/internal/send-photo",
                data=data,
                files=files,
                headers=_internal_headers(),
            )
            r.raise_for_status()
            return r.json()
    r = await _post_telegram_direct(
        "sendPhoto",
        data=data,
        files=files,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


async def telegram_send_media_group_json(
    chat_id: Union[int, str],
    media: List[Dict[str, Any]],
    *,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    base = bot_api_base()
    body = {"chat_id": chat_id, "media": media}
    if base:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{base}/internal/send-media-group-json",
                json=body,
                headers=_internal_headers(),
            )
            r.raise_for_status()
            return r.json()
    r = await _post_telegram_direct("sendMediaGroup", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


async def telegram_send_media_group_multipart(
    chat_id: Union[int, str],
    media_json: str,
    files: List[Tuple[str, Tuple[str, bytes, str]]],
    *,
    parse_mode: Optional[str] = None,
    timeout: float = 60.0,
) -> httpx.Response:
    """
    sendMediaGroup с attach:// полями. files: [(field_name, (filename, bytes, mime)), ...]
    """
    data: Dict[str, str] = {"chat_id": str(chat_id), "media": media_json}
    if parse_mode:
        data["parse_mode"] = parse_mode
    base = bot_api_base()
    if base:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(
                f"{base}/internal/send-media-group-multipart",
                data=data,
                files=files,
                headers=_internal_headers(),
            )
    token = bot_token()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан")
    url = f"{TELEGRAM_DIRECT}{token}/sendMediaGroup"
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, data=data, files=files)


async def telegram_api_get(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Прокси GET-методов Bot API (getChatMemberCount, getChatMember, ...)."""
    base = bot_api_base()
    if base:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{base}/internal/telegram-get",
                json={"method": method, "params": params},
                headers=_internal_headers(),
            )
            try:
                return r.json()
            except Exception:
                return {"ok": False, "description": r.text[:300]}
    return await _get_telegram_direct(method, params)


def telegram_outbound_configured() -> bool:
    """Есть ли способ ходить в Telegram (мост или прямой токен)."""
    return _use_bridge() or bool(bot_token())
