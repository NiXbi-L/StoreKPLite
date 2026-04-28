"""
Прокси Bot API → https://api.telegram.org (для сервера вне РФ).
РФ-сервисы шлют запросы на {API_BASE_URL}/bot-api/... (тот же домен, что API); nginx проксирует сюда.

Заголовок: X-Internal-Token (тот же INTERNAL_TOKEN, что у микросервисов).
Переменные: BOT_TOKEN, INTERNAL_TOKEN.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Union

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
INTERNAL_TOKEN = (os.getenv("INTERNAL_TOKEN") or "").strip() or "internal-secret-token-change-in-production"
TG_BASE = "https://api.telegram.org/bot"

app = FastAPI(title="Timoshka Bot API bridge", version="1")


def _tg_url(method: str) -> str:
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN не настроен на bridge")
    return f"{TG_BASE}{BOT_TOKEN}/{method}"


def _verify_internal(x_internal_token: Optional[str]) -> None:
    if not x_internal_token or x_internal_token.strip() != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid X-Internal-Token")


class SendMessageBody(BaseModel):
    chat_id: Union[int, str]
    text: str
    parse_mode: Optional[str] = None
    reply_markup: Optional[dict] = None


class SendMediaGroupJsonBody(BaseModel):
    chat_id: Union[int, str]
    media: List[Dict[str, Any]]


class TelegramGetBody(BaseModel):
    method: str = Field(..., description="Имя метода Bot API, напр. getChatMember")
    params: Dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "telegram_configured": bool(BOT_TOKEN)}


@app.post("/internal/send-message")
async def send_message(
    body: SendMessageBody,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> dict:
    _verify_internal(x_internal_token)
    payload: Dict[str, Any] = {"chat_id": body.chat_id, "text": body.text}
    if body.parse_mode:
        payload["parse_mode"] = body.parse_mode
    if body.reply_markup is not None:
        payload["reply_markup"] = body.reply_markup
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(_tg_url("sendMessage"), json=payload)
    try:
        data = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail=r.text[:500])
    if not data.get("ok"):
        logger.warning(
            "sendMessage Telegram ok=false http_status=%s chat_id=%s body=%s",
            r.status_code,
            body.chat_id,
            str(data)[:800],
        )
    return data


@app.post("/internal/send-photo")
async def send_photo(
    request: Request,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> dict:
    _verify_internal(x_internal_token)
    form = await request.form()
    chat_id = form.get("chat_id")
    caption = form.get("caption")
    if chat_id is None:
        raise HTTPException(status_code=400, detail="chat_id обязателен")
    photo = form.get("photo")
    if photo is None or not hasattr(photo, "read"):
        raise HTTPException(status_code=400, detail="поле photo (файл) обязательно")
    raw = await photo.read()
    filename = getattr(photo, "filename", None) or "photo.jpg"
    ctype = getattr(photo, "content_type", None) or "image/jpeg"
    data = {"chat_id": str(chat_id)}
    if caption is not None:
        data["caption"] = str(caption)
    files = {"photo": (filename, raw, ctype)}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(_tg_url("sendPhoto"), data=data, files=files)
    try:
        return r.json()
    except Exception:
        raise HTTPException(status_code=502, detail=r.text[:500])


@app.post("/internal/send-media-group-json")
async def send_media_group_json(
    body: SendMediaGroupJsonBody,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> dict:
    _verify_internal(x_internal_token)
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            _tg_url("sendMediaGroup"),
            json={"chat_id": body.chat_id, "media": body.media},
        )
    try:
        return r.json()
    except Exception:
        raise HTTPException(status_code=502, detail=r.text[:500])


@app.post("/internal/send-media-group-multipart")
async def send_media_group_multipart(
    request: Request,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> dict:
    _verify_internal(x_internal_token)
    form = await request.form()
    data_kv: Dict[str, str] = {}
    httpx_files: List[tuple] = []
    for key, val in form.multi_items():
        if hasattr(val, "read"):
            raw = await val.read()
            fn = getattr(val, "filename", None) or key
            ct = getattr(val, "content_type", None) or "application/octet-stream"
            httpx_files.append((key, (fn, raw, ct)))
        else:
            if key in data_kv:
                raise HTTPException(status_code=400, detail=f"Дублируется поле {key}")
            data_kv[key] = str(val)
    if "chat_id" not in data_kv or "media" not in data_kv:
        raise HTTPException(status_code=400, detail="Нужны поля chat_id и media")
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(_tg_url("sendMediaGroup"), data=data_kv, files=httpx_files)
    try:
        return r.json()
    except Exception:
        raise HTTPException(status_code=502, detail=r.text[:500])


@app.post("/internal/telegram-get")
async def telegram_get(
    body: TelegramGetBody,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> dict:
    _verify_internal(x_internal_token)
    method = (body.method or "").strip()
    if not method or "/" in method or not method.replace("_", "").isalnum() or not method[0].isalpha():
        raise HTTPException(status_code=400, detail="Некорректное имя метода")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(_tg_url(method), params=body.params)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": r.text[:300]}
