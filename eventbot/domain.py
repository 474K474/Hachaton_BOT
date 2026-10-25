"""Доменные типы, общие для коллекторов, пайплайна и бота."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

EVENT_TYPES = {
    "conference": "Конференции",
    "meetup": "Митапы",
    "hackathon": "Хакатоны",
    "other": "Другое",
}

AUDIENCES = {
    "dev": "Разработка",
    "pm": "PM / Продукт",
    "data": "Data / ML",
}

CITIES = {
    "spb": "Санкт-Петербург",
    "msk": "Москва",
    "online": "Онлайн",
}

DIGEST_MODES = {
    "instant": "Сразу",
    "daily": "Раз в день",
    "weekly": "Раз в неделю",
}


@dataclass
class RawEvent:
    """То, что возвращает коллектор. Поля, которые источник не дал, остаются пустыми."""

    title: str
    url: str
    source: str
    starts_at: datetime | None = None  # naive UTC
    ends_at: datetime | None = None  # naive UTC
    time_known: bool = False  # известно ли время начала, или только дата
    organizer: str | None = None
    city_hint: str | None = None  # свободный текст про место
    description: str = ""
    extra_text: str = ""  # контекст для классификатора (весь пост, категории и т.п.)
    links: list[str] = field(default_factory=list)


@dataclass
class EventData:
    """Нормализованное и размеченное событие, готовое к записи в БД."""

    id: str
    title: str
    url: str
    source: str
    type: str
    audience: list[str]
    cities: list[str]  # подмножество CITIES
    starts_at: datetime | None
    ends_at: datetime | None
    time_known: bool
    organizer: str | None
    description: str
