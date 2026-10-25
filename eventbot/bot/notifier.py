"""Рассылки: новые события, дайджесты, напоминания."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import async_sessionmaker

from eventbot.bot.formatting import format_digest, format_event
from eventbot.bot.keyboards import event_kb
from eventbot.db import repo
from eventbot.db.models import Subscriber
from eventbot.filters import matches
from eventbot.timeutil import utcnow

log = logging.getLogger(__name__)

MAX_INSTANT_PER_RUN = 5


class Notifier:
    def __init__(self, bot: Bot, sessionmaker: async_sessionmaker, tz: ZoneInfo):
        self.bot = bot
        self.sm = sessionmaker
        self.tz = tz

    async def _send(self, sub: Subscriber, text: str, **kwargs) -> bool:
        for _ in range(2):
            try:
                await self.bot.send_message(sub.chat_id, text, parse_mode="HTML",
                                            disable_web_page_preview=True, **kwargs)
                await asyncio.sleep(0.05)  # лимиты Telegram: ~30 сообщений в секунду
                return True
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except TelegramForbiddenError:
                log.info("user %s blocked the bot — деактивирую", sub.user_id)
                async with self.sm() as s:
                    db_sub = await s.get(Subscriber, sub.user_id)
                    if db_sub:
                        db_sub.active = False
                        await s.commit()
                return False
            except Exception:
                log.exception("send to %s failed", sub.user_id)
                return False
        return False

    async def notify_new(self) -> None:
        """Мгновенные уведомления о новых событиях подписчикам с режимом «Сразу»."""
        async with self.sm() as s:
            events = await repo.unnotified(s)
            subs = await repo.active_subscribers(s, digest="instant")
            now = utcnow()
            events = [e for e in events if e.starts_at is None or e.starts_at >= now]
            for sub in subs:
                done = await repo.delivered_ids(s, sub.user_id)
                todo = [e for e in events if e.id not in done and matches(sub, e)]
                sent = []
                for ev in todo[:MAX_INSTANT_PER_RUN]:
                    if await self._send(sub, format_event(ev, self.tz),
                                        reply_markup=event_kb(ev.id, ev.starts_at is not None)):
                        sent.append(ev.id)
                if len(todo) > MAX_INSTANT_PER_RUN:
                    await self._send(sub, f"…и ещё {len(todo) - MAX_INSTANT_PER_RUN} новых. Все — в /upcoming")
                    sent += [e.id for e in todo[MAX_INSTANT_PER_RUN:]]
                await repo.record_deliveries(s, sub.user_id, sent)
            await repo.mark_notified(s, [e.id for e in await repo.unnotified(s)])

    async def daily_digest(self) -> None:
        async with self.sm() as s:
            since = utcnow() - timedelta(days=1)
            events = await repo.seen_since(s, since)
            for sub in await repo.active_subscribers(s, digest="daily"):
                done = await repo.delivered_ids(s, sub.user_id)
                todo = [e for e in events if e.id not in done and matches(sub, e)]
                if todo and await self._send(sub, format_digest("Новые события за сутки", todo[:30], self.tz)):
                    await repo.record_deliveries(s, sub.user_id, [e.id for e in todo])

    async def weekly_digest(self) -> None:
        """Понедельничная сводка на неделю вперёд — для всех режимов, кроме «Сразу»."""
        async with self.sm() as s:
            now = utcnow()
            week = [e for e in await repo.upcoming(s, now, days=7) if e.starts_at]
            for sub in await repo.active_subscribers(s):
                if sub.digest == "instant":
                    continue
                todo = [e for e in week if matches(sub, e)]
                if todo:
                    await self._send(sub, format_digest("События на этой неделе", todo[:30], self.tz))
                    await repo.record_deliveries(s, sub.user_id, [e.id for e in todo])

    async def reminders(self) -> None:
        async with self.sm() as s:
            due = await repo.due_reminders(s, utcnow(), ahead=timedelta(hours=24))
            for reminder, ev, sub in due:
                await self._send(sub, "⏰ <b>Напоминание: скоро событие</b>\n\n" + format_event(ev, self.tz))
                reminder.sent = True
            await s.commit()
