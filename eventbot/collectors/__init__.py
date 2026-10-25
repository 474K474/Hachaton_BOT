from __future__ import annotations

import httpx

from eventbot.collectors.base import Collector
from eventbot.collectors.telegram_channel import TelegramChannelCollector
from eventbot.collectors.timepad import TimepadCollector
from eventbot.collectors.yandex_events import YandexEventsCollector
from eventbot.config import Settings


def make_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent, "Accept-Language": "ru-RU,ru;q=0.9"},
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
    )


def build_collectors(settings: Settings, client: httpx.AsyncClient) -> list[Collector]:
    collectors: list[Collector] = [
        TelegramChannelCollector(channel, organizer, client, settings.tz)
        for channel, organizer in settings.channels.items()
    ]
    collectors.append(YandexEventsCollector(client, settings.tz))
    if settings.timepad_enabled:
        collectors.append(
            TimepadCollector(
                client,
                token=settings.timepad_token,
                cities=settings.timepad_city_list,
                category_ids=settings.timepad_category_id_list,
            )
        )
    return collectors
