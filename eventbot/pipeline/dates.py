"""Извлечение дат из русского текста анонсов.

Понимает:
  «5 сентября», «5 сентября 2026», «12–13 сентября», «30 сентября – 2 октября»,
  «3 октября в 19:00», «19:00–22:00», «05.11.2026».
Год, если не указан, подбирается относительно даты публикации (ref).
Возвращаются naive-даты в локальном времени источника.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}
_M = (
    r"(январ[ьяе]|феврал[ьяе]|марта?|марте|апрел[ьяе]|ма[йяе]|июн[ьяе]|июл[ьяе]"
    r"|августа?|августе|сентябр[ьяе]|октябр[ьяе]|ноябр[ьяе]|декабр[ьяе])"
)
_DASH = r"\s*(?:[–—\-]|по|до)\s*"
_YEAR = r"(?:\s+(20\d{2}))?"

_RE_CROSS = re.compile(rf"\b(\d{{1,2}})\s+{_M}{_DASH}(\d{{1,2}})\s+{_M}{_YEAR}", re.I)
_RE_RANGE = re.compile(rf"\b(\d{{1,2}})(?:{_DASH}|\s+и\s+)(\d{{1,2}})\s+{_M}{_YEAR}", re.I)
_RE_SINGLE = re.compile(rf"\b(\d{{1,2}})\s+{_M}{_YEAR}", re.I)
_RE_NUMERIC = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b")
_RE_TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


@dataclass
class DateMatch:
    start: datetime
    end: datetime | None
    time_known: bool
    span: tuple[int, int]  # позиция даты в тексте


def _month(word: str) -> int:
    return _MONTHS[word.lower()[:3]]


def _pick_year(day: int, month: int, year: str | None, ref: datetime) -> datetime | None:
    try:
        if year:
            return datetime(int(year), month, day)
        dt = datetime(ref.year, month, day)
    except ValueError:
        return None
    # Анонс не может быть сильно в прошлом: «5 января» в декабре — это следующий год
    if dt < ref - timedelta(days=60):
        try:
            dt = dt.replace(year=ref.year + 1)
        except ValueError:
            return None
    return dt


def _attach_time(text: str, pos: int, start: datetime, end: datetime | None):
    """Ищет время в ближайших ~25 символах после даты."""
    window = text[pos : pos + 25]
    times = _RE_TIME.findall(window)
    if not times:
        return start, end, False
    h, m = map(int, times[0])
    start = start.replace(hour=h, minute=m)
    if len(times) > 1 and end is None:
        h2, m2 = map(int, times[1])
        end = start.replace(hour=h2, minute=m2)
    return start, end, True


def find_dates(text: str, ref: datetime) -> list[DateMatch]:
    """Все даты в тексте, без пересечений, в порядке появления."""
    found: list[DateMatch] = []
    taken: list[tuple[int, int]] = []

    def free(span: tuple[int, int]) -> bool:
        return all(span[1] <= a or span[0] >= b for a, b in taken)

    for m in _RE_CROSS.finditer(text):
        d1, m1, d2, m2, y = m.groups()
        start = _pick_year(int(d1), _month(m1), y, ref)
        end = _pick_year(int(d2), _month(m2), y, ref)
        if start and end:
            if end < start:
                end = end.replace(year=end.year + 1)
            start, _, tk = _attach_time(text, m.end(), start, None)
            found.append(DateMatch(start, end, tk, m.span()))
            taken.append(m.span())

    for m in _RE_RANGE.finditer(text):
        if not free(m.span()):
            continue
        d1, d2, mon, y = m.groups()
        start = _pick_year(int(d1), _month(mon), y, ref)
        end = _pick_year(int(d2), _month(mon), y, ref)
        if start and end and end >= start:
            start, _, tk = _attach_time(text, m.end(), start, None)
            found.append(DateMatch(start, end, tk, m.span()))
            taken.append(m.span())

    for m in _RE_SINGLE.finditer(text):
        if not free(m.span()):
            continue
        d, mon, y = m.groups()
        start = _pick_year(int(d), _month(mon), y, ref)
        if start:
            start, end, tk = _attach_time(text, m.end(), start, None)
            found.append(DateMatch(start, end, tk, m.span()))
            taken.append(m.span())

    for m in _RE_NUMERIC.finditer(text):
        if not free(m.span()):
            continue
        d, mon, y = m.groups()
        try:
            start = datetime(int(y), int(mon), int(d))
        except ValueError:
            continue
        start, end, tk = _attach_time(text, m.end(), start, None)
        found.append(DateMatch(start, end, tk, m.span()))
        taken.append(m.span())

    return sorted(found, key=lambda x: x.span[0])


def first_date(text: str, ref: datetime) -> DateMatch | None:
    dates = find_dates(text, ref)
    return dates[0] if dates else None
