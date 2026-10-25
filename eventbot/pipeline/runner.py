"""Один прогон сбора: все коллекторы → нормализация → БД."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from eventbot.collectors.base import Collector
from eventbot.db import repo
from eventbot.db.models import Event
from eventbot.domain import EventData
from eventbot.pipeline.normalize import to_event_data
from eventbot.timeutil import utcnow

log = logging.getLogger(__name__)


@dataclass
class RunStats:
    per_source: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    new_events: list[Event] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{k}: {v}" for k, v in self.per_source.items()]
        parts += [f"{k}: ОШИБКА {v}" for k, v in self.errors.items()]
        return f"новых: {len(self.new_events)} | " + ", ".join(parts)


async def collect(collectors: list[Collector]) -> tuple[list[EventData], RunStats]:
    stats = RunStats()
    items: dict[str, EventData] = {}
    cutoff = utcnow() - timedelta(days=1)
    for c in collectors:
        try:
            raws = await c.fetch()
        except Exception as e:  # один сломанный источник не должен ронять остальные
            log.exception("collector %s failed", c.name)
            stats.errors[c.name] = f"{type(e).__name__}: {e}"[:200]
            continue
        stats.per_source[c.name] = len(raws)
        if not raws:
            log.warning("collector %s returned 0 events — возможно, сломалась вёрстка", c.name)
        for raw in raws:
            data = to_event_data(raw)
            if data.starts_at and data.starts_at < cutoff:
                continue
            items.setdefault(data.id, data)
    return list(items.values()), stats


async def run_once(collectors: list[Collector], sessionmaker: async_sessionmaker) -> RunStats:
    items, stats = await collect(collectors)
    async with sessionmaker() as session:
        stats.new_events = await repo.save_events(session, items)
    log.info("collect done: %s", stats.summary())
    return stats
