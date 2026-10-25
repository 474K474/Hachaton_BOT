"""Сопоставление события с настройками подписчика."""
from __future__ import annotations

from typing import Protocol


class _Event(Protocol):
    type: str
    cities: list[str]
    audience: list[str]
    organizer: str | None


class _Sub(Protocol):
    types: list[str]
    cities: list[str]
    audience: list[str]
    only_yandex: bool


def is_yandex(organizer: str | None) -> bool:
    if not organizer:
        return False
    low = organizer.lower()
    return "яндекс" in low or "yandex" in low


def matches(sub: _Sub, ev: _Event) -> bool:
    if ev.type not in sub.types:
        return False
    # Город неизвестен — не отбрасываем, лучше показать лишнее, чем пропустить
    if ev.cities and not set(ev.cities) & set(sub.cities):
        return False
    if ev.audience and not set(ev.audience) & set(sub.audience):
        return False
    if sub.only_yandex and not is_yandex(ev.organizer):
        return False
    return True
