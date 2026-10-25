from __future__ import annotations

import hashlib
import re

from eventbot.domain import EventData, RawEvent
from eventbot.pipeline.classify import detect_audience, detect_cities, detect_type

_EDGE_JUNK = re.compile(r"^[\s\W_]+|[\s—–\-:,.;!]+$", re.UNICODE)
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF️‍]+",
    re.UNICODE,
)


def clean_title(title: str) -> str:
    t = _EMOJI.sub(" ", title)
    t = re.sub(r"\s+", " ", t).strip()
    t = _EDGE_JUNK.sub("", t)
    t = t.strip("«»\"' ")
    if len(t) > 200:
        t = t[:197].rstrip() + "…"
    return t


def norm_key(title: str) -> str:
    """Ключ для сравнения названий: без регистра, года, кавычек и пунктуации."""
    t = title.lower().replace("ё", "е")
    t = re.sub(r"\b20\d{2}\b", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def make_id(title: str, starts_at, cities: list[str]) -> str:
    day = starts_at.date().isoformat() if starts_at else "nodate"
    raw = f"{norm_key(title)}|{day}|{','.join(sorted(c for c in cities if c != 'online'))}"
    return hashlib.sha1(raw.encode()).hexdigest()


def to_event_data(raw: RawEvent) -> EventData:
    title = clean_title(raw.title)
    context = " ".join([raw.title, raw.description, raw.extra_text])
    cities = detect_cities(" ".join([raw.city_hint or "", raw.title, raw.extra_text]))
    return EventData(
        id=make_id(title, raw.starts_at, cities),
        title=title,
        url=raw.url,
        source=raw.source,
        type=detect_type(raw.title, context),
        audience=detect_audience(context),
        cities=cities,
        starts_at=raw.starts_at,
        ends_at=raw.ends_at,
        time_known=raw.time_known,
        organizer=raw.organizer,
        description=raw.description.strip()[:1000],
    )
