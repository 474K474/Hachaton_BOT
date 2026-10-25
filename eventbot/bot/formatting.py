from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from eventbot.db.models import Event
from eventbot.domain import AUDIENCES, CITIES
from eventbot.timeutil import utc_to_local

_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"]
_MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
_TYPE_ONE = {"conference": "Конференция", "meetup": "Митап", "hackathon": "Хакатон", "other": "Событие"}
_TYPE_ICON = {"conference": "🎤", "meetup": "☕", "hackathon": "💻", "other": "📌"}


def _day(dt: datetime, year: bool = True) -> str:
    s = f"{dt.day} {_MONTHS[dt.month - 1]}"
    return f"{s} {dt.year}" if year else s


def format_when(ev: Event, tz: ZoneInfo) -> str:
    if ev.starts_at is None:
        return "дата уточняется"
    start = utc_to_local(ev.starts_at, tz)
    end = utc_to_local(ev.ends_at, tz) if ev.ends_at else None
    if end and end.date() != start.date():
        if end.month == start.month:
            return f"{start.day}–{end.day} {_MONTHS[start.month - 1]} {start.year}"
        return f"{_day(start, False)} – {_day(end)}"
    text = _day(start)
    if ev.time_known:
        text += f", {start:%H:%M}"
        if end and end != start:
            text += f"–{end:%H:%M}"
    return text


def format_where(ev: Event) -> str:
    if not ev.cities:
        return "место уточняется"
    order = ["spb", "msk", "online"]
    return ", ".join(CITIES[c] for c in order if c in ev.cities)


def format_event(ev: Event, tz: ZoneInfo) -> str:
    tags = [_TYPE_ONE.get(ev.type, "Событие")]
    tags += [AUDIENCES[a] for a in ev.audience or [] if a in AUDIENCES]
    if ev.organizer:
        tags.append(ev.organizer)
    lines = [
        f"{_TYPE_ICON.get(ev.type, '📌')} <b>{escape(ev.title)}</b>",
        f"🗓 {format_when(ev, tz)}",
        f"📍 {format_where(ev)}",
        f"🏷 {escape(' · '.join(tags))}",
        f'🔗 <a href="{escape(ev.url, quote=True)}">Подробнее и регистрация</a>',
    ]
    return "\n".join(lines)


def format_short(ev: Event, tz: ZoneInfo) -> str:
    """Строка для дайджеста."""
    if ev.starts_at:
        dt = utc_to_local(ev.starts_at, tz)
        when = f"{dt.day} {_MONTHS_SHORT[dt.month - 1]}"
    else:
        when = "скоро"
    where = format_where(ev) if ev.cities else ""
    tail = f" — {where}" if where else ""
    return (f"{_TYPE_ICON.get(ev.type, '📌')} <b>{when}</b> "
            f'<a href="{escape(ev.url, quote=True)}">{escape(ev.title)}</a>{escape(tail)}')


def format_digest(title: str, events: list[Event], tz: ZoneInfo) -> str:
    body = "\n".join(format_short(e, tz) for e in events)
    return f"<b>{escape(title)}</b>\n\n{body}"
