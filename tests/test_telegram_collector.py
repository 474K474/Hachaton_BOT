from datetime import datetime

import httpx
import respx

from eventbot.collectors.telegram_channel import TelegramChannelCollector, extract_events, parse_channel_page
from eventbot.pipeline.normalize import to_event_data


def _events(html, tz):
    out = []
    for post in parse_channel_page(html):
        out += [to_event_data(e) for e in extract_events(post, tz, "Яндекс", "tg:test")]
    return out


def test_parse_posts(fixture_text):
    posts = parse_channel_page(fixture_text("tg_channel.html"))
    assert [p.id for p in posts] == [1794, 1795, 1798, 1799]
    assert posts[1].url == "https://t.me/Yandex4Developers/1795"
    assert posts[1].published.year == 2026


def test_digest_split_into_events(fixture_text, tz):
    events = {e.title: e for e in _events(fixture_text("tg_channel.html"), tz)}
    assert {"deep tech night", "Data Dojo", "Week Offer Security", "Practical ML Conf",
            "Data Driven 2026", "Weekend Offer ML", "Я про бэкенд"} <= set(events)

    pml = events["Practical ML Conf"]  # название на строке над датой
    assert pml.url == "https://pmlconf.yandex.ru/2026/index"
    assert pml.type == "conference" and pml.cities == ["msk", "online"] and "data" in pml.audience

    week = events["Week Offer Security"]  # контекст соседнего события не протекает
    assert week.type == "other" and "data" not in week.audience

    backend = events["Я про бэкенд"]
    assert backend.time_known and backend.starts_at == datetime(2026, 10, 3, 8, 0)  # 11:00 МСК
    assert backend.url == "https://events.yandex.ru/events/yaprobackend"


def test_single_event_post_uses_headline(fixture_text, tz):
    events = _events(fixture_text("tg_channel.html"), tz)
    single = [e for e in events if e.title.startswith("deep tech night:")]
    assert len(single) == 1
    assert single[0].time_known and single[0].cities == ["msk", "online"]


def test_non_event_post_skipped(fixture_text, tz):
    posts = parse_channel_page(fixture_text("tg_channel.html"))
    assert extract_events(posts[0], tz, "Яндекс", "tg") == []


@respx.mock
async def test_fetch_paginates(fixture_text, tz):
    route = respx.get("https://t.me/s/Yandex4Developers").mock(
        side_effect=[httpx.Response(200, text=fixture_text("tg_channel.html")),
                     httpx.Response(200, text="<html></html>")]
    )
    async with httpx.AsyncClient() as client:
        c = TelegramChannelCollector("Yandex4Developers", "Яндекс", client, tz, pages=2)
        c.delay = 0
        events = await c.fetch()
    assert len(events) >= 7
    assert route.calls[1].request.url.params["before"] == "1794"
