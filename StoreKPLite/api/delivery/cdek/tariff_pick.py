"""
Выбор строки тарифа из ответа POST /calculator/tarifflist (СДЭК v2).

Официальная модель ответа (SDK СДЭК `TariffListItem`): поле `delivery_mode` — целое, режим
«склад–склад» = 4. Имена тарифов (`tariff_name`) для фильтра режима недостаточны: без `delivery_mode`
легко выбрать дверь–дверь (как в ЛК при «курьер / курьер»).

В ЛК при «из ПВЗ → в ПВЗ» среди режима 4 берётся нужная карточка по цене; здесь — минимальный delivery_sum.
Тарифы с отдельным словом «возврат» / «return» в названии отбрасываются — иначе «Возврат склад-склад»
мог победить по цене у обычной отправки.
"""
from __future__ import annotations

import os
from typing import Any, Optional


def _norm_tariff_name(row: dict[str, Any]) -> str:
    for key in ("tariff_name", "tariff_name_short", "name", "tariff"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def _tariff_code(row: dict[str, Any]) -> Optional[int]:
    for key in ("tariff_code", "tariff"):
        v = row.get(key)
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def _delivery_sum(row: dict[str, Any]) -> Optional[float]:
    for key in ("delivery_sum", "total_sum", "sum"):
        v = row.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


# Режимы доставки в ответе /calculator/tarifflist (поле delivery_mode), см. DTO СДЭК TariffListItem.
# 1 — дверь-дверь, 2 — дверь-склад, 3 — склад-дверь, 4 — склад-склад.
CDEK_DELIVERY_MODE_WAREHOUSE_WAREHOUSE = 4


def _delivery_mode_value(row: dict[str, Any]) -> Optional[int]:
    """
    Режим в ответе /calculator/tarifflist: snake_case и camelCase (в проде встречается deliveryMode).
    Поле `mode` не трогаем — может относиться к другой сущности.
    """
    keys = ("delivery_mode", "deliveryMode", "mode_id", "modeId")
    for obj in (row, row.get("tariff")):
        if not isinstance(obj, dict):
            continue
        for key in keys:
            v = obj.get(key)
            if v is None:
                continue
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    return None


def _is_return_or_reverse_tariff(norm: str) -> bool:
    """
    Тарифы возврата не подходят для обычной отправки клиенту, но в ответе СДЭК тоже «склад-склад»
    и могли выиграть по минимальной цене. Не используем голое in «возврат» — вхождение в «возврата».
    """
    if not norm:
        return False
    padded = f" {norm} "
    if norm.startswith("возврат") or " возврат" in padded:
        return True
    if "обратн" in norm and "достав" in norm:
        return True
    if norm.startswith("return") or " return" in padded or " reverse" in padded or norm.startswith("reverse"):
        return True
    return False


def _is_sklad_sklad_tariff_name(norm: str) -> bool:
    """Нормализованное имя тарифа — режим склад–склад (RU/EN)."""
    if not norm:
        return False
    # Тире в ответе СДЭК может быть ASCII, en-dash, em-dash.
    dash = ("\u2013", "\u2014", "–", "—")
    compact = norm
    for d in dash:
        compact = compact.replace(d, "-")
    if "склад-склад" in compact or "склад склад" in norm:
        return True
    if "warehouse-warehouse" in norm or "stock-stock" in norm:
        return True
    return False


def pick_tariff_row(
    tariffs: list[dict[str, Any]],
    *,
    destination_is_pickup_point: bool = False,
) -> Optional[dict[str, Any]]:
    """
    Возвращает одну строку тарифа для чекаута / отображения цены.

    destination_is_pickup_point: True, если получатель — ПВЗ СДЭК (в калькулятор передан delivery_point).
    Тогда берём только тарифы «склад-склад» (или delivery_mode=4) и среди них — **самую низкую цену**
    (как в ЛК: «Из ПВЗ» → «В ПВЗ» и самая дешёвая карточка). Раньше приоритет «экономич» в названии давал
    не тот режим (дороже или не склад-склад).

    CDEK_CHECKOUT_TARIFF_STRATEGY:
      - economy_name (по умолчанию): в названии есть «экономич»; при нескольких — минимальная сумма.
      - cheapest_skld_skld: в названии есть «склад-склад», нет «экспресс»; минимальная сумма
        (как на скрине: отсекаем экспресс и магистральный экспресс).
      - first: первый элемент ответа СДЭК (старое поведение).
    """
    rows = [
        t
        for t in tariffs
        if isinstance(t, dict) and not _is_return_or_reverse_tariff(_norm_tariff_name(t))
    ]
    if not rows:
        return None

    strategy = (os.getenv("CDEK_CHECKOUT_TARIFF_STRATEGY") or "economy_name").strip().lower()

    def _min_by_sum(cands: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for r in cands:
            s = _delivery_sum(r)
            if s is not None:
                scored.append((s, r))
        if not scored:
            return cands[0] if cands else None
        scored.sort(key=lambda x: x[0])
        return scored[0][1]

    def _warehouse_warehouse_candidates() -> list[dict[str, Any]]:
        """Тарифы склад–склад: в первую очередь по delivery_mode=4 (официально), иначе по названию."""
        by_mode = [
            r
            for r in rows
            if _delivery_mode_value(r) == CDEK_DELIVERY_MODE_WAREHOUSE_WAREHOUSE
            and "экспресс" not in _norm_tariff_name(r)
        ]
        if by_mode:
            return by_mode
        by_mode_loose = [
            r for r in rows if _delivery_mode_value(r) == CDEK_DELIVERY_MODE_WAREHOUSE_WAREHOUSE
        ]
        if by_mode_loose:
            return by_mode_loose
        sk: list[dict[str, Any]] = []
        for r in rows:
            n = _norm_tariff_name(r)
            if _is_sklad_sklad_tariff_name(n) and "экспресс" not in n:
                sk.append(r)
        if sk:
            return sk
        sk_loose = [r for r in rows if _is_sklad_sklad_tariff_name(_norm_tariff_name(r))]
        return sk_loose

    if destination_is_pickup_point:
        sk_pool = _warehouse_warehouse_candidates()
        if sk_pool:
            # Всегда минимум delivery_sum по склад-склад (стратегия CDEK_CHECKOUT_TARIFF_STRATEGY на ПВЗ не распространяется).
            return _min_by_sum(sk_pool) or sk_pool[0]
        # Нет строки «склад-склад» в названии — не берём слепо первый тариф (часто курьер-курьер).
        _bad_name = (
            "курьер-курьер",
            "дверь-дверь",
            "courier-courier",
            "door-door",
        )
        _softer = [r for r in rows if not any(b in _norm_tariff_name(r) for b in _bad_name)]
        if _softer:
            rows = _softer
        sk_pool = _warehouse_warehouse_candidates()
        if sk_pool:
            return _min_by_sum(sk_pool) or sk_pool[0]
        # Нельзя падать в economy_name / rows[0]: часто это «экономич» дверь-дверь при непрочитанном delivery_mode.
        return None

    if strategy == "first":
        return rows[0]

    if strategy == "cheapest_skld_skld":
        dm4 = [
            r
            for r in rows
            if _delivery_mode_value(r) == CDEK_DELIVERY_MODE_WAREHOUSE_WAREHOUSE
            and "экспресс" not in _norm_tariff_name(r)
        ]
        if dm4:
            return _min_by_sum(dm4) or dm4[0]
        cands = []
        for r in rows:
            n = _norm_tariff_name(r)
            if _is_sklad_sklad_tariff_name(n) and "экспресс" not in n:
                cands.append(r)
        if cands:
            return _min_by_sum(cands) or cands[0]
        return rows[0]

    # economy_name (default): не брать «экономич» без проверки режима — может быть дверь-дверь.
    dm4_econ = [
        r
        for r in rows
        if _delivery_mode_value(r) == CDEK_DELIVERY_MODE_WAREHOUSE_WAREHOUSE
        and "экономич" in _norm_tariff_name(r)
        and "экспресс" not in _norm_tariff_name(r)
    ]
    if dm4_econ:
        return _min_by_sum(dm4_econ) or dm4_econ[0]

    econ = [r for r in rows if "экономич" in _norm_tariff_name(r)]
    if econ:
        return _min_by_sum(econ) or econ[0]

    cands = [
        r
        for r in rows
        if _is_sklad_sklad_tariff_name(_norm_tariff_name(r)) and "экспресс" not in _norm_tariff_name(r)
    ]
    if cands:
        return _min_by_sum(cands) or cands[0]

    return rows[0]


def format_tariff_debug(row: Optional[dict[str, Any]]) -> Optional[str]:
    if not row:
        return None
    code = _tariff_code(row)
    name = row.get("tariff_name") or row.get("name") or ""
    if code is not None and name:
        return f"{code} {name}"
    if code is not None:
        return str(code)
    return str(name)[:120] if name else None
