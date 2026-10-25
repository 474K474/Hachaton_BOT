"""Генерация .ics, чтобы добавить событие в календарь одним нажатием."""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from eventbot.db.models import Event
from eventbot.timeutil import utc_to_local, utcnow


def _esc(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r", "").replace("\n", "\\n"))


def build_ics(ev: Event, tz: ZoneInfo) -> str | None:
    if ev.starts_at is None:
        return None
    if ev.time_known:
        end = ev.ends_at if ev.ends_at and ev.ends_at > ev.starts_at else ev.starts_at + timedelta(hours=2)
        dtstart = f"DTSTART:{ev.starts_at:%Y%m%dT%H%M%S}Z"
        dtend = f"DTEND:{end:%Y%m%dT%H%M%S}Z"
    else:
        start = utc_to_local(ev.starts_at, tz).date()
        end_day = utc_to_local(ev.ends_at, tz).date() if ev.ends_at else start
        dtstart = f"DTSTART;VALUE=DATE:{start:%Y%m%d}"
        dtend = f"DTEND;VALUE=DATE:{end_day + timedelta(days=1):%Y%m%d}"
    location = ", ".join({"spb": "Санкт-Петербург", "msk": "Москва", "online": "Онлайн"}[c]
                         for c in ev.cities or [] if c in ("spb", "msk", "online"))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//eventbot//RU",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{ev.id}@eventbot",
        f"DTSTAMP:{utcnow():%Y%m%dT%H%M%S}Z",
        dtstart,
        dtend,
        f"SUMMARY:{_esc(ev.title)}",
        f"DESCRIPTION:{_esc((ev.description or '')[:500] + chr(10) + ev.url)}",
        f"URL:{ev.url}",
    ]
    if location:
        lines.append(f"LOCATION:{_esc(location)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"
