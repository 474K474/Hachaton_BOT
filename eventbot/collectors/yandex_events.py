"""events.yandex.ru — официальный сайт событий Яндекса.

На октябрь 2026 сайт отдаёт заглушку («О новых событиях расскажем позже»),
а анонсы идут через @Yandex4Developers. Коллектор написан так, чтобы молча
вернуть пустой список на заглушке и заработать, когда сайт вернётся:
ищет ссылки /events/<slug> на главной и разбирает страницы событий
через JSON-LD (schema.org/Event) или og-теги.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from eventbot.collectors.base import Collector
from eventbot.domain import RawEvent
from eventbot.pipeline.dates import first_date
from eventbot.timeutil import aware_to_utc, local_to_utc, utcnow, utc_to_local

log = logging.getLogger(__name__)

BASE = "https://events.yandex.ru/"
_EVENT_PATH = re.compile(r"^/events/[\w\-]+/?$")
_PLACEHOLDER = re.compile(r"расскажем позже", re.I)


class YandexEventsCollector(Collector):
    name = "events.yandex.ru"
    max_pages = 30

    def __init__(self, client: httpx.AsyncClient, tz: ZoneInfo):
        super().__init__(client)
        self.tz = tz

    async def fetch(self) -> list[RawEvent]:
        resp = await self.get(BASE)
        if is_placeholder(resp.text):
            log.info("events.yandex.ru: заглушка, событий нет")
            return []
        events = []
        for url in find_event_links(resp.text)[: self.max_pages]:
            try:
                page = await self.get(url)
            except httpx.HTTPError as e:
                log.warning("events.yandex.ru: %s: %s", url, e)
                continue
            ev = parse_event_page(page.text, url, self.tz)
            if ev:
                events.append(ev)
        return events


def is_placeholder(html: str) -> bool:
    h1 = BeautifulSoup(html, "lxml").find("h1")
    return bool(h1 and _PLACEHOLDER.search(h1.get_text()))


def find_event_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    seen: dict[str, None] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        path = re.sub(r"^https?://events\.yandex\.ru", "", href).split("?")[0]
        if _EVENT_PATH.match(path):
            seen[urljoin(BASE, path)] = None
    return list(seen)


def parse_event_page(html: str, url: str, tz: ZoneInfo) -> RawEvent | None:
    if is_placeholder(html):
        return None
    soup = BeautifulSoup(html, "lxml")

    ld = _find_jsonld_event(soup)
    if ld:
        start = _parse_iso(ld.get("startDate"), tz)
        end = _parse_iso(ld.get("endDate"), tz)
        loc = ld.get("location") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        place = " ".join(filter(None, [
            loc.get("name") if isinstance(loc, dict) else None,
            json.dumps(loc.get("address"), ensure_ascii=False) if isinstance(loc, dict) and loc.get("address") else None,
            "онлайн" if "Online" in str(ld.get("eventAttendanceMode", "")) or loc.get("@type") == "VirtualLocation" else None,
        ]))
        return RawEvent(
            title=ld.get("name") or "",
            url=url,
            source="events.yandex.ru",
            starts_at=start,
            ends_at=end,
            time_known=bool(ld.get("startDate") and "T" in ld["startDate"]),
            organizer="Яндекс",
            city_hint=place,
            description=_strip_html(ld.get("description") or ""),
            extra_text=place,
        )

    title = _meta(soup, "og:title") or (soup.title.get_text(strip=True) if soup.title else "")
    if not title:
        return None
    desc = _meta(soup, "og:description") or ""
    body = soup.get_text(" ", strip=True)
    ref = utc_to_local(utcnow(), tz).replace(tzinfo=None)
    d = first_date(desc, ref) or first_date(body[:3000], ref)
    return RawEvent(
        title=title,
        url=url,
        source="events.yandex.ru",
        starts_at=local_to_utc(d.start, tz) if d else None,
        ends_at=local_to_utc(d.end, tz) if d and d.end else None,
        time_known=bool(d and d.time_known),
        organizer="Яндекс",
        city_hint=f"{desc} {body[:2000]}",
        description=desc,
        extra_text=body[:2000],
    )


def _find_jsonld_event(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for item in items:
            if isinstance(item, dict) and "Event" in str(item.get("@type", "")):
                return item
    return None


def _meta(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    return tag.get("content") if tag else None


def _parse_iso(value: str | None, tz: ZoneInfo) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return aware_to_utc(dt) if dt.tzinfo else local_to_utc(dt, tz)


def _strip_html(text: str) -> str:
    return BeautifulSoup(text, "lxml").get_text(" ", strip=True) if "<" in text else text
