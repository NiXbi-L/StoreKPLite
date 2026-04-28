"""
Расчёт габаритов и веса сборной посылки по списку товаров.
Используется для одной накладной на всю посылку (CDEK и т.п.).

Модель укладки стопкой: база — посылка с максимальной площадью (L×W),
высота — сумма высот всех посылок.
"""
from typing import Any

# Дефолты для одного товара, если габариты/вес не заданы (шмотки)
DEFAULT_WEIGHT_KG = 1.0
DEFAULT_LENGTH_CM = 40
DEFAULT_WIDTH_CM = 30
DEFAULT_HEIGHT_CM = 10


def _int_or_none(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _float_or_none(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def aggregate_parcel_dimensions(
    line_items: list[dict[str, Any]],
    *,
    default_weight_kg: float = DEFAULT_WEIGHT_KG,
    default_length_cm: int = DEFAULT_LENGTH_CM,
    default_width_cm: int = DEFAULT_WIDTH_CM,
    default_height_cm: int = DEFAULT_HEIGHT_CM,
    packing_factor: float = 1.25,
) -> dict[str, Any]:
    """
    Считает суммарный вес и габариты одной посылки по списку позиций.
    Укладка стопкой: база — посылка с максимальной площадью (L×W), высота — сумма высот.

    :param line_items: список словарей с ключами quantity (int), опционально
        estimated_weight_kg, length_cm, width_cm, height_cm (на единицу товара).
    :param default_*: значения по умолчанию, если у позиции не заданы размеры/вес.
    :param packing_factor: не используется (оставлен для совместимости).
    :return: dict с ключами weight_gram, length_cm, width_cm, height_cm, total_volume_cm3.
    """
    total_weight_kg = 0.0
    boxes: list[tuple[int, int, int]] = []  # (length, width, height) на каждую единицу

    for row in line_items:
        qty = max(0, int(row.get("quantity") or 1))
        if qty == 0:
            continue
        w = _float_or_none(row.get("estimated_weight_kg"))
        if w is None:
            w = default_weight_kg
        w = max(0.0, w)
        l_cm = _int_or_none(row.get("length_cm")) or default_length_cm
        w_cm = _int_or_none(row.get("width_cm")) or default_width_cm
        h_cm = _int_or_none(row.get("height_cm")) or default_height_cm
        l_cm = max(1, l_cm)
        w_cm = max(1, w_cm)
        h_cm = max(1, h_cm)

        total_weight_kg += qty * w
        for _ in range(qty):
            boxes.append((l_cm, w_cm, h_cm))

    weight_gram = max(1, round(total_weight_kg * 1000))

    if not boxes:
        length_cm = max(1, default_length_cm)
        width_cm = max(1, default_width_cm)
        height_cm = max(1, default_height_cm)
        total_volume_cm3 = length_cm * width_cm * height_cm
    else:
        # База — посылка с максимальной площадью (L×W)
        base_box = max(boxes, key=lambda b: b[0] * b[1])
        base_l, base_w, _ = base_box
        # Длина >= ширина для единообразия
        length_cm = max(base_l, base_w)
        width_cm = min(base_l, base_w)
        # Высота — сумма высот всех посылок
        height_cm = max(1, sum(b[2] for b in boxes))
        total_volume_cm3 = length_cm * width_cm * height_cm

    return {
        "weight_gram": weight_gram,
        "length_cm": length_cm,
        "width_cm": width_cm,
        "height_cm": height_cm,
        "total_volume_cm3": total_volume_cm3,
        "total_weight_kg": round(total_weight_kg, 3),
    }


def build_line_items_for_parcel(
    order_data_items: list[dict[str, Any]],
    items_by_id: dict[int, Any],
    *,
    default_weight_kg: float = DEFAULT_WEIGHT_KG,
    default_length_cm: int = DEFAULT_LENGTH_CM,
    default_width_cm: int = DEFAULT_WIDTH_CM,
    default_height_cm: int = DEFAULT_HEIGHT_CM,
) -> list[dict[str, Any]]:
    """
    Превращает order_data["items"] и словарь товаров (Item по id) в список
    позиций с полями quantity, estimated_weight_kg, length_cm, width_cm, height_cm
    для передачи в aggregate_parcel_dimensions.

    :param order_data_items: список из order.order_data["items"] (item_id, quantity, ...).
    :param items_by_id: словарь {item.id: item} с объектами Item (имеют estimated_weight_kg, length_cm, width_cm, height_cm).
    """
    line_items = []
    for row in order_data_items or []:
        item_id = row.get("item_id")
        qty = max(0, int(row.get("quantity") or 1))
        if qty == 0:
            continue
        item = items_by_id.get(item_id) if item_id is not None else None
        if item is not None:
            w = _float_or_none(getattr(item, "estimated_weight_kg", None))
            w_use = float(w) if w is not None else float(default_weight_kg)
            w_use = max(0.0, w_use)
            l_cm = _int_or_none(getattr(item, "length_cm", None))
            w_cm = _int_or_none(getattr(item, "width_cm", None))
            h_cm = _int_or_none(getattr(item, "height_cm", None))
            line_items.append({
                "quantity": qty,
                "estimated_weight_kg": w,
                "length_cm": l_cm,
                "width_cm": w_cm,
                "height_cm": h_cm,
                "weight_gram_per_unit": max(1, round(w_use * 1000)),
            })
        else:
            w = _float_or_none(row.get("estimated_weight_kg"))
            w_use = float(w) if w is not None else float(default_weight_kg)
            w_use = max(0.0001, w_use)
            l_cm = _int_or_none(row.get("length_cm")) or default_length_cm
            w_cm = _int_or_none(row.get("width_cm")) or default_width_cm
            h_cm = _int_or_none(row.get("height_cm")) or default_height_cm
            l_cm = max(1, l_cm)
            w_cm = max(1, w_cm)
            h_cm = max(1, h_cm)
            line_items.append({
                "quantity": qty,
                "estimated_weight_kg": w,
                "length_cm": l_cm,
                "width_cm": w_cm,
                "height_cm": h_cm,
                "weight_gram_per_unit": max(1, round(w_use * 1000)),
            })
    return line_items
