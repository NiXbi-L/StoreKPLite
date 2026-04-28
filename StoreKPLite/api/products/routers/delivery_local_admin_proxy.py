"""
Прокси админских настроек локальной доставки (ПВЗ, курьер, СДЭК отправитель) в delivery-service.

Админка ходит на /api/products/admin/delivery-local/..., nginx отдаёт это в products-service;
оттуда запрос уходит на delivery-service /admin/... с тем же JWT.

Нужен обход, если /api/delivery/ на фронте nginx указывает не туда или в контейнере delivery
старый образ delivery без delivery_local_admin: страница «Способы доставки» снова работает при живом delivery в сети Docker.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from api.shared.auth import require_admin_type

logger = logging.getLogger(__name__)

router = APIRouter()
require_admin = require_admin_type("admin")

DELIVERY_SERVICE_URL = os.getenv("DELIVERY_SERVICE_URL", "http://delivery-service:8005").rstrip("/")


async def _proxy_to_delivery(request: Request, delivery_path: str) -> Response:
    auth = request.headers.get("authorization")
    if not auth:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")

    url = f"{DELIVERY_SERVICE_URL}{delivery_path}"
    body: bytes = await request.body()
    hdrs: dict[str, str] = {"Authorization": auth}
    ct = request.headers.get("content-type")
    if ct and body and request.method.upper() not in ("GET", "HEAD"):
        hdrs["Content-Type"] = ct

    content: Optional[bytes] = None
    if body and request.method.upper() not in ("GET", "HEAD"):
        content = body

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.request(request.method.upper(), url, content=content, headers=hdrs)
    except httpx.RequestError as e:
        logger.error("delivery_local_admin_proxy: не удалось достучаться до delivery-service: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Сервис доставки недоступен",
        ) from e

    media = resp.headers.get("content-type", "application/json")
    return Response(content=resp.content, status_code=resp.status_code, media_type=media)


@router.get("/admin/delivery-local/local-pickup-points")
async def proxy_get_pickup_points(request: Request, _admin=Depends(require_admin)):
    return await _proxy_to_delivery(request, "/admin/local-pickup-points")


@router.post("/admin/delivery-local/local-pickup-points")
async def proxy_post_pickup_points(request: Request, _admin=Depends(require_admin)):
    return await _proxy_to_delivery(request, "/admin/local-pickup-points")


@router.put("/admin/delivery-local/local-pickup-points/{point_id}")
async def proxy_put_pickup_point(point_id: int, request: Request, _admin=Depends(require_admin)):
    return await _proxy_to_delivery(request, f"/admin/local-pickup-points/{point_id}")


@router.delete("/admin/delivery-local/local-pickup-points/{point_id}")
async def proxy_delete_pickup_point(point_id: int, request: Request, _admin=Depends(require_admin)):
    return await _proxy_to_delivery(request, f"/admin/local-pickup-points/{point_id}")


@router.get("/admin/delivery-local/local-courier-config")
async def proxy_get_courier_config(request: Request, _admin=Depends(require_admin)):
    return await _proxy_to_delivery(request, "/admin/local-courier-config")


@router.put("/admin/delivery-local/local-courier-config")
async def proxy_put_courier_config(request: Request, _admin=Depends(require_admin)):
    return await _proxy_to_delivery(request, "/admin/local-courier-config")


@router.get("/admin/delivery-local/cdek-sender-config")
async def proxy_get_cdek_sender(request: Request, _admin=Depends(require_admin)):
    return await _proxy_to_delivery(request, "/admin/cdek-sender-config")


@router.put("/admin/delivery-local/cdek-sender-config")
async def proxy_put_cdek_sender(request: Request, _admin=Depends(require_admin)):
    return await _proxy_to_delivery(request, "/admin/cdek-sender-config")
