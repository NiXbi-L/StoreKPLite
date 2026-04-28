"""Хелперы для заказов (итог по позициям и т.д.)."""
import os
from typing import Any, Dict, List, Optional, Tuple


def cdek_delivery_calc_insurance_extras(
    delivery_method_code: Optional[str],
    order_lines: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Поля для POST …/calculate-cost в delivery-service: объявленная стоимость и страховка в POST /calculator/tariff.
    Включается при CDEK_ADD_INSURANCE_TO_ORDERS=1 (тот же флаг, что добавляет services в POST /orders).

    order_lines: цены до скидок чекаута (промо/«скидка владельца»). Иначе при 100% скидке сумма товаров
    становится 0 и СДЭК не получает страховую базу — в предпросмотре остаётся только базовый тариф.
    """
    if (delivery_method_code or "").strip() != "CDEK":
        return {}
    if (os.getenv("CDEK_ADD_INSURANCE_TO_ORDERS") or "0").strip().lower() not in ("1", "true", "yes", "on"):
        return {}
    decl = sum(float(r.get("price") or 0) * int(r.get("quantity") or 1) for r in order_lines)
    if decl <= 0:
        return {}
    return {"cdek_declared_value_rub": decl, "cdek_add_insurance": True}


def compute_order_total(
    order_data: Any,
    exclude_returned: bool = False,
) -> Optional[float]:
    """Итоговая сумма заказа по order_data['items'] (price * quantity).
    Если exclude_returned=True, позиции с returned=True не учитываются (итог после возвратов).
    """
    if not order_data or not isinstance(order_data, dict):
        return None
    items = order_data.get("items") or []
    if not items:
        return None
    if exclude_returned:
        items = [item for item in items if not item.get("returned")]
    total = sum(
        float(item.get("price", 0)) * int(item.get("quantity", 1))
        for item in items
    )
    return round(total, 2)


def line_totals_for_order_items(
    order_data: Any,
    *,
    exclude_returned: bool = True,
) -> Tuple[List[float], float]:
    """
    Суммы по строкам тем же правилом, что и compute_order_total: price * quantity без округления по строке,
    итог — round(sum, 2). Нужен для чека и платежа, чтобы не расходились копейки.
    """
    if not order_data or not isinstance(order_data, dict):
        return [], 0.0
    items = order_data.get("items") or []
    if exclude_returned:
        items = [item for item in items if not item.get("returned")]
    line_totals: List[float] = []
    for item in items:
        t = float(item.get("price", 0) or 0) * int(item.get("quantity", 1) or 1)
        line_totals.append(t)
    goods = round(sum(line_totals), 2) if line_totals else 0.0
    return line_totals, goods


def sum_yookassa_receipt_items_rub(receipt_items: List[Any]) -> float:
    """Сумма полей amount.value в позициях чека ЮKassa (переданных в finance)."""
    total = 0.0
    for it in receipt_items or []:
        if not isinstance(it, dict):
            continue
        amt = it.get("amount") or {}
        v = amt.get("value")
        if v is not None:
            total += float(v)
    return round(total, 2)


def adjust_yookassa_receipt_sum_to_target(
    receipt_items: List[Dict[str, Any]],
    target_rub: float,
) -> None:
    """
    Подгоняет сумму позиций чека под целевую сумму платежа (in-place).
    Последняя позиция, у которой после коррекции value >= 0.01; иначе идём к предыдущим.
    """
    if not receipt_items:
        return
    target = round(float(target_rub), 2)
    current = sum_yookassa_receipt_items_rub(receipt_items)
    diff = round(target - current, 2)
    if abs(diff) < 0.005:
        return
    for idx in range(len(receipt_items) - 1, -1, -1):
        it = receipt_items[idx]
        if not isinstance(it, dict):
            continue
        amt = it.setdefault("amount", {})
        v = float(amt.get("value", 0) or 0)
        new_v = round(v + diff, 2)
        if new_v >= 0.01:
            amt["value"] = f"{new_v:.2f}"
            return


def delivery_cost_from_order_snapshot(order_data: Any) -> float:
    """delivery_snapshot.delivery_cost_rub из order_data (0 если нет)."""
    if not order_data or not isinstance(order_data, dict):
        return 0.0
    snap = order_data.get("delivery_snapshot") or {}
    d = snap.get("delivery_cost_rub")
    if d is None:
        return 0.0
    try:
        return float(d)
    except (TypeError, ValueError):
        return 0.0


def compute_order_amount_due(
    order_data: Any,
    tryon_discount_rub: float = 0.0,
    delivery_cost_rub: float = 0.0,
    exclude_returned: bool = True,
) -> float:
    """
    Сумма к оплате: товары − скидка за примерки + доставка (не ниже 0).
    Округление до целых рублей — как при выставлении оплаты и в миниаппе (без копеек).
    Цены в позициях заказа по-прежнему могут быть с копейками.
    """
    goods = float(compute_order_total(order_data, exclude_returned=exclude_returned) or 0)
    disc = float(tryon_discount_rub or 0)
    deliv = float(delivery_cost_rub or 0)
    raw = max(0.0, goods - disc + deliv)
    return float(round(raw))
