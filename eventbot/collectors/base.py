from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

import httpx

from eventbot.domain import RawEvent


class Collector(ABC):
    """Источник событий. Чтобы добавить новый — унаследуйся и реализуй fetch()."""

    name: str = "base"
    #: пауза между запросами к одному сайту, чтобы не нагружать его
    delay: float = 1.0

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @abstractmethod
    async def fetch(self) -> list[RawEvent]: ...

    async def get(self, url: str, **kwargs) -> httpx.Response:
        resp = await self.client.get(url, **kwargs)
        resp.raise_for_status()
        await asyncio.sleep(self.delay)
        return resp
