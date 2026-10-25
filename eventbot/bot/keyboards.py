from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from eventbot.db.models import Subscriber
from eventbot.domain import AUDIENCES, CITIES, DIGEST_MODES, EVENT_TYPES


class Toggle(CallbackData, prefix="t"):
    group: str  # cities | types | audience | yandex | digest | done
    value: str


class EvAction(CallbackData, prefix="e"):
    action: str  # ics | remind
    id: str


class More(CallbackData, prefix="m"):
    kind: str  # all | yandex | hackathons
    offset: int


def _mark(on: bool) -> str:
    return "✅" if on else "▫️"


def settings_kb(sub: Subscriber) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in CITIES.items():
        kb.button(text=f"{_mark(key in sub.cities)} {label}", callback_data=Toggle(group="cities", value=key))
    for key, label in EVENT_TYPES.items():
        kb.button(text=f"{_mark(key in sub.types)} {label}", callback_data=Toggle(group="types", value=key))
    for key, label in AUDIENCES.items():
        kb.button(text=f"{_mark(key in sub.audience)} {label}", callback_data=Toggle(group="audience", value=key))
    kb.button(text=f"{_mark(sub.only_yandex)} Только Яндекс", callback_data=Toggle(group="yandex", value="1"))
    for key, label in DIGEST_MODES.items():
        mark = "🔘" if sub.digest == key else "⚪️"
        kb.button(text=f"{mark} {label}", callback_data=Toggle(group="digest", value=key))
    kb.button(text="Готово", callback_data=Toggle(group="done", value="1"))
    # города 3 | типы 2+2 | аудитория 3 | яндекс 1 | частота 3 | готово 1
    kb.adjust(3, 2, 2, 3, 1, 3, 1)
    return kb.as_markup()


SETTINGS_TEXT = (
    "<b>Настройки</b>\n\n"
    "Ряд 1 — города, ряды 2–3 — типы событий, ряд 4 — для кого, "
    "дальше — фильтр «только Яндекс» и как часто присылать новые события.\n"
    "Нажимай, чтобы включить или выключить."
)


def event_kb(event_id: str, has_date: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if has_date:
        kb.button(text="📅 В календарь", callback_data=EvAction(action="ics", id=event_id))
        kb.button(text="🔔 Напомнить", callback_data=EvAction(action="remind", id=event_id))
    return kb.as_markup()


def more_kb(kind: str, offset: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Показать ещё", callback_data=More(kind=kind, offset=offset))
    return kb.as_markup()
