"""
HTML-лендинг для превью ссылок на товар (Open Graph) и редирект браузеров в SPA.
"""
from __future__ import annotations

import html
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.database.database import get_session
from api.products.models.item import Item
from api.products.models.item_photo import ItemPhoto
from api.products.models.item_stock import ItemStock
from api.products.utils.finance_context import get_finance_price_context
from api.products.utils.item_pricing import compute_item_customer_price_rub

router = APIRouter()

_TEMPLATE = (Path(__file__).resolve().parent.parent / "templates" / "share_catalog.html").read_text(
    encoding="utf-8"
)

# Публичный origin сайта (og:image, редирект в витрину)
SHARE_PUBLIC_WEB_ORIGIN = (os.getenv("SHARE_PUBLIC_WEB_ORIGIN") or "https://matchwear.ru").rstrip("/")
# Публичный путь страницы шаринга (nginx: location ^~ /share/catalog/ → products-service)
SHARE_PUBLIC_CATALOG_SHARE_PATH = (os.getenv("SHARE_PUBLIC_CATALOG_SHARE_PATH") or "/share/catalog").rstrip("/")

# UA похож на обычный браузер (редирект в SPA); остальным отдаём HTML с метой
_BROWSER_UA_RE = re.compile(
    r"(mozilla/.+\(.*?)(chrome|safari|firefox|edg/|edgios|crios|fxios|opr/|samsungbrowser|version/)",
    re.I | re.DOTALL,
)
_CRAWLER_HINT_RE = re.compile(
    r"bot\b|spider|crawl|slurp|mediapartners|facebookexternalhit|facebot|"
    r"telegrambot|whatsapp|vkshare|slackbot|linkedinbot|discordbot|pinterest|"
    r"googlebot|bingpreview|yandex|mail\.ru|embedly|quora link preview",
    re.I,
)


def _should_redirect_browser_to_spa(user_agent: Optional[str]) -> bool:
    if not user_agent or not user_agent.strip():
        return False
    ua = user_agent.strip()
    if _CRAWLER_HINT_RE.search(ua):
        return False
    return bool(_BROWSER_UA_RE.search(ua))


def _format_price_line(price_rub: Decimal, fixed_price_rub: Optional[Decimal], has_stock: bool) -> str:
    p = int(price_rub.quantize(Decimal("1")))
    if has_stock and fixed_price_rub is not None:
        f = int(fixed_price_rub.quantize(Decimal("1")))
        if f != p:
            return f"В наличии — {f} ₽ · под заказ ~{p} ₽"
        return f"{f} ₽"
    return f"~{p} ₽"


def _sizes_line(item: Item, distinct_stock_sizes: list[str]) -> str:
    raw = item.size
    sizes: list[str] = []
    if isinstance(raw, list):
        sizes = [str(s).strip() for s in raw if s is not None and str(s).strip()]
    elif isinstance(raw, str) and raw.strip():
        sizes = [raw.strip()]
    if not sizes and distinct_stock_sizes:
        sizes = distinct_stock_sizes
    if not sizes:
        return ""
    return "Размеры: " + ", ".join(sizes[:24])


def _absolute_image_url(file_path: Optional[str]) -> str:
    if file_path and str(file_path).strip():
        path = str(file_path).strip().lstrip("/")
        return f"{SHARE_PUBLIC_WEB_ORIGIN}/{path}"
    return f"{SHARE_PUBLIC_WEB_ORIGIN}/miniapp/applogo/Logo192.jpg"


def _render_html(
    *,
    title: str,
    description: str,
    share_page_url: str,
    og_image: str,
    app_url: str,
) -> str:
    def esc(s: str) -> str:
        return html.escape(s, quote=True)

    return (
        _TEMPLATE.replace("{{ title }}", esc(title))
        .replace("{{ description }}", esc(description))
        .replace("{{ share_page_url }}", esc(share_page_url))
        .replace("{{ og_image }}", esc(og_image))
        .replace("{{ app_url }}", esc(app_url))
    )


@router.get("/share/catalog/{item_id}", response_class=HTMLResponse)
async def share_catalog_item(
    request: Request,
    item_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Превью для мессенджеров (мета в HTML) и редирект обычных браузеров на hash-роут витрины.
    """
    result = await session.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        return HTMLResponse("<!DOCTYPE html><html><head><title>Товар не найден</title></head>"
                            "<body><p>Товар не найден</p></body></html>", status_code=404)

    stock_sizes_result = await session.execute(
        select(ItemStock.size)
        .where(and_(ItemStock.item_id == item.id, ItemStock.quantity > 0))
        .distinct()
    )
    distinct_sizes = [str(r[0]).strip() for r in stock_sizes_result.all() if r[0] is not None and str(r[0]).strip()]
    has_stock = len(distinct_sizes) > 0

    ctx = await get_finance_price_context()
    price_rub = compute_item_customer_price_rub(
        item,
        ctx.rate_with_margin,
        ctx.delivery_cost_per_kg,
        yuan_markup_before_rub_percent=ctx.yuan_markup_before_rub_percent,
        customer_price_acquiring_factor=ctx.customer_price_acquiring_factor,
    )

    fixed = item.fixed_price
    fixed_dec: Optional[Decimal] = None
    if fixed is not None and has_stock:
        fixed_dec = Decimal(str(fixed))

    photos_result = await session.execute(
        select(ItemPhoto)
        .where(ItemPhoto.item_id == item.id)
        .order_by(func.coalesce(ItemPhoto.sort_order, 999999).asc(), ItemPhoto.id)
    )
    photos = photos_result.scalars().all()
    first_path = photos[0].file_path if photos else None

    title = (item.name or "Товар").strip() or "Товар"
    price_part = _format_price_line(price_rub, fixed_dec, has_stock)
    sizes_part = _sizes_line(item, distinct_sizes)
    description = price_part + ((" · " + sizes_part) if sizes_part else "")

    share_page_url = f"{SHARE_PUBLIC_WEB_ORIGIN}{SHARE_PUBLIC_CATALOG_SHARE_PATH}/{item_id}"
    app_url = f"{SHARE_PUBLIC_WEB_ORIGIN}/#/main/catalog/{item_id}"
    og_image = _absolute_image_url(first_path)

    ua = request.headers.get("user-agent")
    if _should_redirect_browser_to_spa(ua):
        return RedirectResponse(url=app_url, status_code=302)

    body = _render_html(
        title=title,
        description=description,
        share_page_url=share_page_url,
        og_image=og_image,
        app_url=app_url,
    )
    return HTMLResponse(content=body)
