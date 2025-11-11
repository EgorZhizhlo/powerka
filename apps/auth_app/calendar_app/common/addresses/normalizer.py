import re
from typing import Optional, Dict, Tuple


STREET_TYPES = {
    r"ул\.?": "улица",
    r"улица": "улица",
    r"пр-?т\.?": "проспект",
    r"просп\.?": "проспект",
    r"проспект": "проспект",
    r"пер\.?": "переулок",
    r"переулок": "переулок",
    r"б-?р\.?|бул\.?": "бульвар",
    r"бульвар": "бульвар",
    r"ш\.?": "шоссе",
    r"шоссе": "шоссе",
    r"наб\.?": "набережная",
    r"набережная": "набережная",
    r"пл\.?": "площадь",
    r"площадь": "площадь",
    r"проезд": "проезд",
    r"аллея": "аллея",
    r"тракт": "тракт",
    r"квартал": "квартал",
    r"микрорайон|мкр\.?": "микрорайон",
}

TOKENS = {
    r"(?:д|дом)\.?": "дом",
    r"(?:к|корп|корпус)\.?": "корпус",
    r"(?:с|стр|строение)\.?": "строение",
    r"(?:лит|литера)\.?": "литера",
    r"(?:кв|квартира)\.?": "квартира",
    r"(?:оф|офис)\.?": "офис",
    r"(?:комн|комната)\.?": "комната",
}

NUM_PATTERN = r"([0-9]+[a-zа-я]?(?:[/\-][0-9a-zа-я]+)?)"


def _pre_split_compounds(s: str) -> str:
    """
    Распиливает склейки: 5к2 -> 'дом 5 корпус 2', 5/2 -> 'дом 5 корпус 2',
    5с1 -> 'дом 5 строение 1', 5литА -> 'дом 5 литера А'
    """
    # 5к2 / 5k2 / 5/2 -> дом 5 корпус 2
    s = re.sub(r"\b(\d+)\s*[кk/]\s*(\d+)\b",
               r"дом \1 корпус \2", s, flags=re.IGNORECASE)
    # 5с1 / 5c1 -> дом 5 строение 1
    s = re.sub(r"\b(\d+)\s*[сc]\s*(\d+)\b",
               r"дом \1 строение \2", s, flags=re.IGNORECASE)
    # 5литА / 5 лита -> дом 5 литера А
    s = re.sub(r"\b(\d+)\s*лит\.?\s*([a-zа-я])\b",
               r"дом \1 литера \2", s, flags=re.IGNORECASE)
    return s


def _normalize_tokens(s: str) -> str:
    s = s.replace("ё", "е").lower()
    s = _pre_split_compounds(s)
    # убрать пунктуацию в пробелы, схлопнуть
    s = re.sub(r"[,\.;]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # нормализуем типы улиц
    for pat, repl in STREET_TYPES.items():
        s = re.sub(rf"\b{pat}\b", repl, s, flags=re.IGNORECASE)

    # нормализуем строительные и unit-токены
    for pat, repl in TOKENS.items():
        s = re.sub(rf"\b{pat}\b", repl, s, flags=re.IGNORECASE)

    return s


def _extract_number(token_name: str, s: str) -> Tuple[Optional[str], str]:
    """
    Ищет фрагмент 'token_name NUM' (пример: 'дом 5', 'корпус 2', 'квартира 12а')
    Возвращает найденный номер и строку без этого фрагмента.
    """
    rx = re.compile(
        rf"\b{token_name}\b\s*[:#\.\-–—/]?\s*{NUM_PATTERN}", flags=re.IGNORECASE)
    m = rx.search(s)
    if not m:
        return None, s
    num = m.group(1)
    s = s[:m.start()] + s[m.end():]
    s = re.sub(r"\s+", " ", s).strip()
    return num, s


def parse_address(addr: str) -> Dict[str, Optional[str]]:
    """
    Возвращает:
      street_type, street_name, дом, корпус, строение, литера, unit_type, unit_number
    """
    s = _normalize_tokens(addr)

    house, s = _extract_number("дом", s)
    korp,  s = _extract_number("корпус", s)
    stroi, s = _extract_number("строение", s)
    lit,   s = _extract_number("литера", s)

    unit_type = None
    unit_number = None
    for ut in ("квартира", "офис", "комната"):
        num, s2 = _extract_number(ut, s)
        if num:
            unit_type, unit_number = ut, num
            s = s2
            break

    # street_type + street_name
    street_type = None
    street_name = None
    tokens = s.split()
    if tokens:
        if tokens[0] in set(STREET_TYPES.values()):
            street_type = tokens[0]
            name_tokens = tokens[1:]
        else:
            name_tokens = tokens

        # убрать мусорные общие слова
        name_tokens = [t for t in name_tokens if t not in {"адрес"}]
        # оставить буквы/цифры/дефисы
        cleaned = [re.sub(r"[^a-zа-я0-9\-]", "", t) for t in name_tokens]
        cleaned = [t for t in cleaned if t]
        if cleaned:
            street_name = " ".join(cleaned)

    return {
        "street_type": street_type,
        "street_name": street_name,
        "дом": house,
        "корпус": korp,
        "строение": stroi,
        "литера": lit,
        "unit_type": unit_type,
        "unit_number": unit_number,
    }


def address_key(addr: str) -> str:
    """
    Канонический ключ для сравнения адресов (с сохранением юнита).
    Разные квартиры/офисы -> разные ключи.
    """
    p = parse_address(addr)
    parts = [
        f"type={p['street_type'] or ''}",
        f"name={p['street_name'] or ''}",
        f"dom={p['дом'] or ''}",
        f"korp={p['корпус'] or ''}",
        f"str={p['строение'] or ''}",
        f"lit={p['литера'] or ''}",
        f"unit={p['unit_type'] or ''}",
        f"unum={p['unit_number'] or ''}",
    ]
    return "|".join(parts)
