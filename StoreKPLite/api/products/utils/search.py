"""
Умный поиск по товарам: транслит (латиница ↔ кириллица) и варианты для нечёткого совпадения.

Пример: запрос "ofwhite" находит товары с названием "Офвайт", "офвайт" и т.д.
"""

from typing import List

# Латиница → кириллица (однобуквенно + частые сочетания для брендов)
_LATIN_TO_CYR = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "й", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "w": "в", "x": "кс", "y": "й", "z": "з",
    "wh": "в", "ck": "к", "sh": "ш", "ch": "ч", "th": "з", "ee": "и", "oo": "у",
}
# Частые бренды/слова: латинское написание → как обычно пишут кириллицей
_KNOWN_LATIN_TO_CYRILLIC: dict[str, str] = {
    "ofwhite": "офвайт", "off white": "офвайт", "off-white": "офвайт",
    "nike": "найк", "adidas": "адидас", "puma": "пума",
    "gucci": "гучи", "balenciaga": "баленсиага", "supreme": "супрем",
    "jordan": "джордан", "new balance": "нью баланс", "newbalance": "нью баланс",
    "reebok": "рибок", "lacoste": "лакост", "champion": "чемпион",
    "tommy": "томми", "hilfiger": "хилфигер", "calvin klein": "кальвин кляйн",
    "zara": "зара", "hm": "эйч эм", "uniqlo": "юникло",
}
# Кириллица → латиница (для обратного поиска: пользователь ввёл "офвайт" — ищем и "ofwhite" в БД)
_CYR_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _transliterate_latin_to_cyrillic(text: str) -> str:
    """Переводит латиницу в кириллицу посимвольно (для подстановки в поиск)."""
    result = []
    text_lower = text.lower()
    i = 0
    while i < len(text_lower):
        two = text_lower[i : i + 2]
        one = text_lower[i]
        if two in _LATIN_TO_CYR:
            result.append(_LATIN_TO_CYR[two])
            i += 2
            continue
        if one in _LATIN_TO_CYR:
            result.append(_LATIN_TO_CYR[one])
        else:
            result.append(one)
        i += 1
    return "".join(result)


def _transliterate_cyrillic_to_latin(text: str) -> str:
    """Кириллица → латиница (для поиска по полям, где могла быть латиница)."""
    result = []
    for c in text.lower():
        result.append(_CYR_TO_LATIN.get(c, c))
    return "".join(result)


def get_search_patterns(query: str) -> List[str]:
    """
    Возвращает список строк для умного поиска по одному запросу:
    - исходная строка (очищенная);
    - латиница → кириллица;
    - кириллица → латиница;
    - известные бренды (ofwhite → офвайт и т.д.).

    Удобно использовать: ищем по имени/описанию по любому из вариантов (OR).
    """
    if not query or not query.strip():
        return []
    q = query.strip()
    patterns = [q]
    # Известные бренды: подставляем кириллический вариант
    q_lower = q.lower()
    for lat, cyr in _KNOWN_LATIN_TO_CYRILLIC.items():
        if lat in q_lower or q_lower in lat:
            patterns.append(cyr)
        # Если запрос целиком бренд — добавляем кириллицу
        if q_lower == lat or q_lower.replace(" ", "") == lat.replace(" ", ""):
            patterns.append(cyr)
    # Транслит: латиница → кириллица
    if any(c.isascii() and c.isalpha() for c in q):
        patterns.append(_transliterate_latin_to_cyrillic(q))
    # Транслит: кириллица → латиница (на случай если в БД название латиницей)
    if any(ord(c) > 127 for c in q):
        patterns.append(_transliterate_cyrillic_to_latin(q))
    # Уникальные непустые
    seen = set()
    out = []
    for p in patterns:
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def text_matches_any_pattern(text: str, patterns: List[str]) -> bool:
    """Проверяет, что в text (например name или description) есть хотя бы один из patterns (без учёта регистра)."""
    if not text or not patterns:
        return False
    text_lower = (text or "").lower()
    for p in patterns:
        if p and p.lower() in text_lower:
            return True
    return False


def text_fuzzy_matches(query: str, text: str, score_cutoff: int = 65) -> bool:
    """
    Нечёткое совпадение (с опечатками): запрос «of wite» совпадает с текстом «off white odsy».
    Использует rapidfuzz: partial_ratio для подстроки, token_set_ratio для набора слов.
    score_cutoff 0–100; 65 допускает 1–2 опечатки.
    """
    if not query or not query.strip() or not text:
        return False
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return False
    q = query.strip().lower()
    t = (text or "").lower()
    # partial_ratio: короткий запрос внутри длинного текста (опечатки учитываются)
    if fuzz.partial_ratio(q, t, score_cutoff=score_cutoff) >= score_cutoff:
        return True
    # token_set_ratio: порядок слов не важен, совпадение по словам с опечатками
    if fuzz.token_set_ratio(q, t, score_cutoff=score_cutoff) >= score_cutoff:
        return True
    return False
