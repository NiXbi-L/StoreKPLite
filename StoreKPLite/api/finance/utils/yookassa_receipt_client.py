"""Запросы к API чеков ЮKassa (GET /v3/receipts)."""
from __future__ import annotations

import logging
from os import getenv
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

YOOKASSA_RECEIPTS_URL = "https://api.yookassa.ru/v3/receipts"
YOOKASSA_SHOP_ID = getenv("YOOKASSA_SHOP_ID")
YOOKASSA_API_TOKEN = getenv("YOOKASSA_API_TOKEN")


async def list_receipts_for_yookassa_payment(yookassa_payment_id: str) -> List[Dict[str, Any]]:
    if not YOOKASSA_SHOP_ID or not YOOKASSA_API_TOKEN:
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                YOOKASSA_RECEIPTS_URL,
                params={"payment_id": yookassa_payment_id},
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_API_TOKEN),
                headers={"Content-Type": "application/json"},
            )
            if r.status_code != 200:
                logger.warning(
                    "ЮKassa GET receipts payment_id=%s: HTTP %s %s",
                    yookassa_payment_id,
                    r.status_code,
                    (r.text or "")[:400],
                )
                return []
            data = r.json()
            lst = data.get("items")
            return lst if isinstance(lst, list) else []
    except Exception as e:
        logger.warning("Ошибка запроса списка чеков ЮKassa: %s", e)
        return []


async def get_yookassa_receipt(receipt_id: str) -> Optional[Dict[str, Any]]:
    if not YOOKASSA_SHOP_ID or not YOOKASSA_API_TOKEN or not receipt_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{YOOKASSA_RECEIPTS_URL}/{receipt_id}",
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_API_TOKEN),
                headers={"Content-Type": "application/json"},
            )
            if r.status_code != 200:
                logger.warning(
                    "ЮKassa GET receipt %s: HTTP %s %s",
                    receipt_id,
                    r.status_code,
                    (r.text or "")[:400],
                )
                return None
            return r.json()
    except Exception as e:
        logger.warning("Ошибка запроса чека ЮKassa %s: %s", receipt_id, e)
        return None


def pick_payment_receipt_id(receipts: List[Dict[str, Any]]) -> Optional[str]:
    """ID чека типа payment: сначала succeeded, иначе любой payment."""
    chosen: Optional[str] = None
    for rec in receipts:
        if rec.get("type") == "payment" and rec.get("status") == "succeeded":
            rid = rec.get("id")
            if isinstance(rid, str) and rid:
                return rid
    for rec in receipts:
        if rec.get("type") == "payment":
            rid = rec.get("id")
            if isinstance(rid, str) and rid:
                chosen = rid
                break
    return chosen
