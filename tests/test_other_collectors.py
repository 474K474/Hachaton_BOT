import json

import httpx
import respx

from eventbot.collectors.timepad import TimepadCollector, parse_event
from eventbot.collectors.yandex_events import (YandexEventsCollector, find_event_links,
                                               is_placeholder, parse_event_page)

PLACEHOLDER = """<html><head><title>События Яндекса</title></head><body>
<h1>О новых событиях расскажем позже</h1><p>…</p></body></html>"""

EVENT_PAGE = """<html><head><title>Я про бэкенд</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Event",
"name":"Я про бэкенд","startDate":"2026-11-14T11:00:00+03:00","endDate":"2026-11-14T19:00:00+03:00",
"eventAttendanceMode":"https://schema.org/MixedEventAttendanceMode",
"location":{"@type":"Place","name":"Офис Яндекса","address":"Москва, ул. Льва Толстого, 16"},
"description":"Конференция для бэкенд-разработчиков"}</script></head><body></body></html>"""

LISTING = """<html><body><h1>События</h1>
<a href="/events/yaprobackend">Я про бэкенд</a>
<a href="https://events.yandex.ru/events/data-driven-2026?utm=1">Data Driven</a>
<a href="/about">О нас</a></body></html>"""


def test_yandex_placeholder():
    assert is_placeholder(PLACEHOLDER)
    assert parse_event_page(PLACEHOLDER, "https://events.yandex.ru/events/x", None) is None


def test_yandex_links_and_jsonld(tz):
    assert find_event_links(LISTING) == [
        "https://events.yandex.ru/events/yaprobackend",
        "https://events.yandex.ru/events/data-driven-2026",
    ]
    ev = parse_event_page(EVENT_PAGE, "https://events.yandex.ru/events/yaprobackend", tz)
    assert ev.title == "Я про бэкенд" and ev.time_known
    assert ev.starts_at.hour == 8  # UTC
    assert "Москва" in ev.city_hint


@respx.mock
async def test_yandex_collector_on_placeholder(tz):
    respx.get("https://events.yandex.ru/").mock(return_value=httpx.Response(200, text=PLACEHOLDER))
    async with httpx.AsyncClient() as client:
        c = YandexEventsCollector(client, tz)
        c.delay = 0
        assert await c.fetch() == []


TP_EVENT = {
    "id": 1,
    "name": "Frontend Meetup #12",
    "url": "https://example.timepad.ru/event/1/",
    "starts_at": "2026-11-20T19:00:00+0300",
    "ends_at": "2026-11-20T22:00:00+0300",
    "description_short": "Доклады про React и производительность",
    "location": {"city": "Санкт-Петербург", "address": "Невский пр., 1"},
    "organization": {"name": "Frontend SPb"},
    "categories": [{"id": 452, "name": "ИТ и интернет"}],
}


def test_timepad_parse():
    ev = parse_event(TP_EVENT)
    assert ev.title == "Frontend Meetup #12" and ev.organizer == "Frontend SPb"
    assert ev.starts_at.hour == 16 and ev.time_known
    assert "Санкт-Петербург" in ev.city_hint


def test_timepad_filters_non_it():
    item = {**TP_EVENT, "name": "Мастер-класс по керамике", "description_short": "",
            "categories": [{"id": 1, "name": "Хобби"}]}
    assert parse_event(item) is None


@respx.mock
async def test_timepad_collector_resolves_category():
    respx.get("https://api.timepad.ru/v1/dictionary/event_categories").mock(
        return_value=httpx.Response(200, json={"values": [{"id": 452, "name": "ИТ и интернет"},
                                                          {"id": 1, "name": "Хобби"}]}))
    events_route = respx.get("https://api.timepad.ru/v1/events").mock(
        return_value=httpx.Response(200, json={"total": 1, "values": [TP_EVENT]}))
    async with httpx.AsyncClient() as client:
        c = TimepadCollector(client, token="secret")
        c.delay = 0
        events = await c.fetch()
    assert len(events) == 1
    req = events_route.calls[0].request
    assert req.url.params["category_ids"] == "452"
    assert req.headers["Authorization"] == "Bearer secret"
    assert "Санкт-Петербург" in req.url.params["cities"]
    json.dumps(events[0].__dict__, default=str)  # сериализуемо
