"""Сборка приложения: БД, бот, коллекторы, планировщик."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from eventbot.bot.handlers import router
from eventbot.bot.notifier import Notifier
from eventbot.collectors import build_collectors, make_client
from eventbot.config import get_settings
from eventbot.db.session import init_db, make_engine, make_sessionmaker
from eventbot.pipeline.runner import RunStats, run_once

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="upcoming", description="Ближайшие события"),
    BotCommand(command="yandex", description="События Яндекса"),
    BotCommand(command="hackathons", description="Хакатоны"),
    BotCommand(command="settings", description="Фильтры и частота"),
    BotCommand(command="help", description="Что умеет бот"),
]


async def run_bot() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан — скопируй .env.example в .env и заполни")

    engine = make_engine(settings.database_url)
    await init_db(engine)
    sm = make_sessionmaker(engine)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    notifier = Notifier(bot, sm, settings.tz)
    client = make_client(settings)
    collectors = build_collectors(settings, client)
    lock = asyncio.Lock()

    async def collect_job() -> RunStats:
        async with lock:  # не запускать два сбора одновременно
            stats = await run_once(collectors, sm)
            await notifier.notify_new()
            return stats

    scheduler = AsyncIOScheduler(timezone=settings.tz)
    scheduler.add_job(collect_job, "interval", hours=settings.collect_interval_hours,
                      next_run_time=datetime.now(settings.tz) + timedelta(seconds=15),
                      id="collect", max_instances=1, coalesce=True)
    scheduler.add_job(notifier.daily_digest, "cron", hour=settings.digest_hour, minute=0, id="daily")
    scheduler.add_job(notifier.weekly_digest, "cron", day_of_week="mon",
                      hour=settings.digest_hour, minute=5, id="weekly")
    scheduler.add_job(notifier.reminders, "interval", minutes=30, id="reminders")

    dp = Dispatcher(
        sessionmaker=sm,
        tz=settings.tz,
        admin_ids=settings.admin_id_set,
        collect_job=collect_job,
    )
    dp.include_router(router)

    await bot.set_my_commands(COMMANDS)
    scheduler.start()
    log.info("bot started; collectors: %s", ", ".join(c.name for c in collectors))
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await client.aclose()
        await bot.session.close()
        await engine.dispose()


async def collect_cli(save: bool) -> None:
    """Один прогон сбора без бота — для отладки парсеров."""
    from eventbot.pipeline.runner import collect

    settings = get_settings()
    async with make_client(settings) as client:
        collectors = build_collectors(settings, client)
        if save:
            engine = make_engine(settings.database_url)
            await init_db(engine)
            stats = await run_once(collectors, make_sessionmaker(engine))
            await engine.dispose()
            print(stats.summary())
            return
        items, stats = await collect(collectors)
    for e in sorted(items, key=lambda x: (x.starts_at is None, x.starts_at or datetime.max)):
        when = e.starts_at.strftime("%Y-%m-%d %H:%M UTC") if e.starts_at else "без даты"
        print(f"[{e.source}] {when} | {e.type} | {','.join(e.audience)} | "
              f"{','.join(e.cities)} | {e.title}\n    {e.url}")
    print(f"\nИтого: {len(items)} | {stats.summary()}")
