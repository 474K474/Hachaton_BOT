"""Timepad — через официальное API (https://dev.timepad.ru).

Берём события в нужных городах из категории «ИТ» и дополнительно
отсеиваем не-IT по ключевым словам. Токен передаётся как Bearer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx

from eventbot.collectors.base import Collector
from eventbot.domain import RawEvent
from eventbot.pipeline.classify import looks_it_related
from eventbot.timeutil import aware_to_utc, utcnow

log = logging.getLogger(__name__)

API = "https://api.timepad.ru/v1"
FIELDS = "location,organization,categories,description_short,ends_at"


class TimepadCollector(Collector):
    name = "timepad"
    delay = 0.5
    page_size = 100
    max_pages = 3
    days_ahead = 90

    def __init__(self, client: httpx.AsyncClient, token: str = "", cities: list[str] | None = None,
                 category_ids: list[int] | None = None):
        super().__init__(client)
        self.token = token
        self.cities = cities or ["Санкт-Петербург", "Москва"]
        self.category_ids = list(category_ids or [])

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def resolve_categories(self) -> list[int]:
        if self.category_ids:
            return self.category_ids
        resp = await self.get(f"{API}/dictionary/event_categories", headers=self.headers)
        values = resp.json().get("values", [])
        ids = [c["id"] for c in values if _is_it_category(c.get("name", ""))]
        if ids:
            self.category_ids = ids
        else:
            log.warning("timepad: категория ИТ не найдена, фильтрую только по ключевым словам")
        return ids

    async def fetch(self) -> list[RawEvent]:
        cats = await self.resolve_categories()
        now = utcnow()
        params = {
            "limit": self.page_size,
            "sort": "+starts_at",
            "fields": FIELDS,
            "cities": ",".join(self.cities + ["Без города"]),
            "starts_at_min": now.strftime("%Y-%m-%dT%H:%M:%S+0000"),
            "starts_at_max": (now + timedelta(days=self.days_ahead)).strftime("%Y-%m-%dT%H:%M:%S+0000"),
            "moderation_statuses": "featured,shown",
        }
        if cats:
            params["category_ids"] = ",".join(map(str, cats))

        events: list[RawEvent] = []
        for page in range(self.max_pages):
            params["skip"] = page * self.page_size
            resp = await self.get(f"{API}/events", params=params, headers=self.headers)
            data = resp.json()
            values = data.get("values", [])
            for item in values:
                ev = parse_event(item)
                if ev:
                    events.append(ev)
            if len(values) < self.page_size or params["skip"] + len(values) >= data.get("total", 0):
                break
        return events


def _is_it_category(name: str) -> bool:
    low = name.lower()
    return low.startswith("ит") or " ит" in low or "it" in low.split()


def parse_event(item: dict) -> RawEvent | None:
    name = item.get("name") or ""
    url = item.get("url") or ""
    if not name or not url:
        return None
    categories = " ".join(c.get("name", "") for c in item.get("categories") or [])
    desc = item.get("description_short") or ""
    if not looks_it_related(f"{name} {desc} {categories}"):
        return None
    loc = item.get("location") or {}
    city = loc.get("city") or ""
    place = " ".join(filter(None, [city, loc.get("address")]))
    if not city or city == "Без города":
        place = f"онлайн {place}"
    org = (item.get("organization") or {}).get("name")
    return RawEvent(
        title=name,
        url=url,
        source="timepad",
        starts_at=_parse(item.get("starts_at")),
        ends_at=_parse(item.get("ends_at")),
        time_known=bool(item.get("starts_at")),
        organizer=org,
        city_hint=place,
        description=desc,
        extra_text=categories,
    )


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Timepad отдаёт «2026-11-05T19:00:00+0300»
        return aware_to_utc(datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z"))
    except ValueError:
        try:
            return aware_to_utc(datetime.fromisoformat(value))
        except ValueError:
            return None
