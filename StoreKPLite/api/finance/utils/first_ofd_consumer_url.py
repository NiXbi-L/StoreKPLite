"""Публичная ссылка на кассовый документ на сайте Первого ОФД (как в ЛК ЮKassa)."""
from __future__ import annotations

from os import getenv
from typing import Any, Dict, Optional
from urllib.parse import urlencode

# База URL без query; при смене ОФД задаётся через env.
FIRST_OFD_TICKET_BASE = getenv("FIRST_OFD_TICKET_BASE", "https://consumer.1-ofd.ru/ticket").rstrip("/")
# Параметр `n` в ссылке 1-ОФД зависит от типа чека в ЮKassa; значения по умолчанию совпадают с ЛК для прихода/возврата.
_FIRST_OFD_N_PAYMENT = int(getenv("FIRST_OFD_TICKET_N_PAYMENT", "1"))
_FIRST_OFD_N_REFUND = int(getenv("FIRST_OFD_TICKET_N_REFUND", "2"))


def first_ofd_ticket_url_from_yookassa_receipt(receipt: Dict[str, Any]) -> Optional[str]:
    """
    Собрать URL consumer.1-ofd.ru/ticket по объекту чека ЮKassa (GET /v3/receipts/{id}).
    Нужны status=succeeded и три фискальных поля.
    """
    if (receipt.get("status") or "").lower() != "succeeded":
        return None
    fn = receipt.get("fiscal_storage_number")
    fd = receipt.get("fiscal_document_number")
    fp = receipt.get("fiscal_attribute")
    if fn is None or fd is None or fp is None:
        return None
    rtype = (receipt.get("type") or "payment").lower()
    n = _FIRST_OFD_N_REFUND if rtype == "refund" else _FIRST_OFD_N_PAYMENT
    q = urlencode({"fn": str(fn), "i": str(fd), "fp": str(fp), "n": str(n)})
    return f"{FIRST_OFD_TICKET_BASE}?{q}"
