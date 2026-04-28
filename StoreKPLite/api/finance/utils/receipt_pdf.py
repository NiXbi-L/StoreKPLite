# -*- coding: utf-8 -*-
"""PDF-справка по составу, переданному в ЮKassa (не заменяет фискальный чек ОФД)."""
from __future__ import annotations

import glob
import logging
import os
import uuid
from io import BytesIO
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)


def _register_cyrillic_font():
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return None
    font_name = "CyrillicReceiptPDF"
    try:
        pdfmetrics.getFont(font_name)
        return font_name
    except Exception:
        pass

    candidates: List[str] = []
    here = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(here, "fonts", "DejaVuSans.ttf")
    candidates.append(bundled)

    if os.name == "nt":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        candidates.extend(
            [
                os.path.join(windir, "Fonts", "arial.ttf"),
                os.path.join(windir, "Fonts", "Arial.ttf"),
                os.path.join(windir, "Fonts", "segoeui.ttf"),
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            ]
        )
        for pattern in (
            "/usr/share/fonts/truetype/dejavu/*.ttf",
            "/usr/share/fonts/**/DejaVuSans.ttf",
        ):
            for path in sorted(glob.glob(pattern, recursive=True)):
                if path not in candidates and "DejaVuSans" in os.path.basename(path):
                    if "Oblique" in path or "Bold" in path:
                        continue
                    candidates.append(path)

    seen = set()
    ordered = []
    for p in candidates:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)

    for path in ordered:
        if path and os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, path))
                return font_name
            except Exception:
                continue
    return None


def build_payment_receipt_pdf_bytes(
    *,
    order_id: int,
    payment_id: int,
    amount: str,
    yookassa_payment_id: Optional[str],
    yookassa_receipt_id: Optional[str],
    receipt_registration: Optional[str],
    items: List[Dict[str, Any]],
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    cyr = _register_cyrillic_font()
    if not cyr:
        logger.warning(
            "receipt_pdf: не найден TTF с кириллицей (DejaVu/Arial). "
            "В Docker установите fonts-dejavu-core или положите DejaVuSans.ttf в api/finance/utils/fonts/"
        )
        cyr = "Helvetica"

    base_n = styles["Normal"]
    _sid = uuid.uuid4().hex[:10]
    normal = ParagraphStyle(
        name=f"RecNormal_{_sid}",
        fontName=cyr,
        fontSize=base_n.fontSize,
        leading=base_n.leading + 2,
    )
    title = ParagraphStyle(
        name=f"RecTitle_{_sid}",
        fontName=cyr,
        fontSize=16,
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        name=f"RecH2_{_sid}",
        fontName=cyr,
        fontSize=13,
        spaceBefore=10,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        name=f"RecCell_{_sid}",
        fontName=cyr,
        fontSize=8,
        leading=10,
    )

    story: list = []
    story.append(Paragraph("Справка по составу чека (ЮKassa)", title))
    story.append(
        Paragraph(
            "<i>Документ сформирован из данных, переданных в ЮKassa при оплате. "
            "Не является фискальным чеком. Фискальный чек покупатель получает на электронную почту; "
            "проверка в ОФД — по данным из личного кабинета ЮKassa.</i>",
            normal,
        )
    )
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Заказ:</b> №{order_id}", normal))
    story.append(Paragraph(f"<b>Внутренний ID платежа:</b> {payment_id}", normal))
    story.append(Paragraph(f"<b>Сумма платежа:</b> {amount} ₽", normal))
    if yookassa_payment_id:
        story.append(Paragraph(f"<b>ID платежа ЮKassa:</b> {yookassa_payment_id}", normal))
    if yookassa_receipt_id:
        story.append(Paragraph(f"<b>ID чека ЮKassa:</b> {yookassa_receipt_id}", normal))
    if receipt_registration:
        story.append(Paragraph(f"<b>Регистрация чека (платёж):</b> {receipt_registration}", normal))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Позиции", h2))

    def _cell(text: str) -> Paragraph:
        return Paragraph(escape(str(text)), cell_style)

    table_data = [
        [_cell("№"), _cell("Описание"), _cell("Кол-во"), _cell("Сумма")],
    ]
    for i, it in enumerate(items, 1):
        desc = str(it.get("description", "—"))[:240]
        qty = it.get("quantity", "")
        amt = it.get("amount")
        if isinstance(amt, dict):
            val = amt.get("value", "")
        else:
            val = str(amt) if amt is not None else ""
        table_data.append([_cell(str(i)), _cell(desc), _cell(str(qty)), _cell(str(val))])

    t = Table(table_data, colWidths=[12 * mm, 98 * mm, 22 * mm, 38 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t)
    doc.build(story)
    return buf.getvalue()
