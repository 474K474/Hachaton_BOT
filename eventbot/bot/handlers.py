from __future__ import annotations

from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from eventbot.bot.formatting import format_event
from eventbot.bot.ics import build_ics
from eventbot.bot.keyboards import SETTINGS_TEXT, EvAction, More, Toggle, event_kb, more_kb, settings_kb
from eventbot.db import repo
from eventbot.db.models import Event, Subscriber
from eventbot.filters import is_yandex, matches
from eventbot.pipeline.runner import RunStats
from eventbot.timeutil import utcnow

router = Router()
PAGE = 5

HELP = (
    "Я собираю IT-конференции, митапы и хакатоны в Петербурге и Москве — "
    "в первую очередь от Яндекса.\n\n"
    "/upcoming — ближайшие события по твоим фильтрам\n"
    "/yandex — все события Яндекса\n"
    "/hackathons — хакатоны\n"
    "/settings — города, типы, аудитория, частота\n"
    "/stop — отписаться от рассылки\n\n"
    "У каждого события есть кнопки «В календарь» и «Напомнить» (за сутки до начала)."
)


async def _sub(sm: async_sessionmaker, msg: Message) -> Subscriber:
    async with sm() as s:
        sub, _ = await repo.get_or_create_subscriber(s, msg.from_user.id, msg.chat.id)
        return sub


@router.message(CommandStart())
async def cmd_start(message: Message, sessionmaker: async_sessionmaker):
    async with sessionmaker() as s:
        sub, created = await repo.get_or_create_subscriber(s, message.from_user.id, message.chat.id)
    greeting = "Привет! " if created else "С возвращением! "
    await message.answer(greeting + HELP)
    await message.answer(SETTINGS_TEXT, reply_markup=settings_kb(sub))


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP)


@router.message(Command("settings"))
async def cmd_settings(message: Message, sessionmaker: async_sessionmaker):
    sub = await _sub(sessionmaker, message)
    await message.answer(SETTINGS_TEXT, reply_markup=settings_kb(sub))


@router.message(Command("stop"))
async def cmd_stop(message: Message, sessionmaker: async_sessionmaker):
    async with sessionmaker() as s:
        sub = await s.get(Subscriber, message.from_user.id)
        if sub:
            sub.active = False
            await s.commit()
    await message.answer("Отписал от рассылки. Вернуться — /start")


@router.callback_query(Toggle.filter())
async def on_toggle(cb: CallbackQuery, callback_data: Toggle, sessionmaker: async_sessionmaker):
    async with sessionmaker() as s:
        sub, _ = await repo.get_or_create_subscriber(s, cb.from_user.id, cb.message.chat.id)
        group, value = callback_data.group, callback_data.value
        if group == "done":
            await cb.message.edit_reply_markup(reply_markup=None)
            await cb.answer("Сохранено")
            await cb.message.answer("Готово! Ближайшие события — /upcoming")
            return
        if group in ("cities", "types", "audience"):
            current = list(getattr(sub, group))
            if value in current:
                if len(current) == 1:
                    await cb.answer("Нужно оставить хотя бы один вариант", show_alert=True)
                    return
                current.remove(value)
            else:
                current.append(value)
            setattr(sub, group, current)  # новое значение, чтобы SQLAlchemy заметил изменение JSON
        elif group == "yandex":
            sub.only_yandex = not sub.only_yandex
        elif group == "digest":
            sub.digest = value
        await s.commit()
    await cb.message.edit_reply_markup(reply_markup=settings_kb(sub))
    await cb.answer()


# ---------- списки событий ----------

def _select(kind: str, sub: Subscriber, events: list[Event]) -> list[Event]:
    if kind == "yandex":
        return [e for e in events if is_yandex(e.organizer)]
    if kind == "hackathons":
        return [e for e in events if e.type == "hackathon" and (not e.cities or set(e.cities) & set(sub.cities))]
    return [e for e in events if matches(sub, e)]


async def _send_list(message: Message, sm: async_sessionmaker, tz: ZoneInfo, user_id: int,
                     kind: str, offset: int = 0):
    async with sm() as s:
        sub, _ = await repo.get_or_create_subscriber(s, user_id, message.chat.id)
        events = _select(kind, sub, await repo.upcoming(s, utcnow()))
    if not events:
        await message.answer("Пока ничего не нашёл. Попробуй расширить фильтры в /settings")
        return
    page = events[offset : offset + PAGE]
    for ev in page:
        await message.answer(format_event(ev, tz), parse_mode="HTML", disable_web_page_preview=True,
                             reply_markup=event_kb(ev.id, ev.starts_at is not None))
    rest = len(events) - offset - len(page)
    if rest > 0:
        await message.answer(f"Ещё {rest}", reply_markup=more_kb(kind, offset + PAGE))


@router.message(Command("upcoming"))
async def cmd_upcoming(message: Message, sessionmaker: async_sessionmaker, tz: ZoneInfo):
    await _send_list(message, sessionmaker, tz, message.from_user.id, "all")


@router.message(Command("yandex"))
async def cmd_yandex(message: Message, sessionmaker: async_sessionmaker, tz: ZoneInfo):
    await _send_list(message, sessionmaker, tz, message.from_user.id, "yandex")


@router.message(Command("hackathons"))
async def cmd_hackathons(message: Message, sessionmaker: async_sessionmaker, tz: ZoneInfo):
    await _send_list(message, sessionmaker, tz, message.from_user.id, "hackathons")


@router.callback_query(More.filter())
async def on_more(cb: CallbackQuery, callback_data: More, sessionmaker: async_sessionmaker, tz: ZoneInfo):
    await cb.message.delete()
    await _send_list(cb.message, sessionmaker, tz, cb.from_user.id, callback_data.kind, callback_data.offset)
    await cb.answer()


@router.callback_query(EvAction.filter(F.action == "ics"))
async def on_ics(cb: CallbackQuery, callback_data: EvAction, sessionmaker: async_sessionmaker, tz: ZoneInfo):
    async with sessionmaker() as s:
        ev = await s.get(Event, callback_data.id)
    ics = build_ics(ev, tz) if ev else None
    if not ics:
        await cb.answer("У события пока нет даты", show_alert=True)
        return
    await cb.message.answer_document(BufferedInputFile(ics.encode(), filename="event.ics"),
                                     caption=ev.title[:200])
    await cb.answer()


@router.callback_query(EvAction.filter(F.action == "remind"))
async def on_remind(cb: CallbackQuery, callback_data: EvAction, sessionmaker: async_sessionmaker):
    async with sessionmaker() as s:
        await repo.get_or_create_subscriber(s, cb.from_user.id, cb.message.chat.id)
        if not await s.get(Event, callback_data.id):
            await cb.answer("Событие не найдено", show_alert=True)
            return
        added = await repo.add_reminder(s, cb.from_user.id, callback_data.id)
    await cb.answer("Напомню за сутки до начала" if added else "Напоминание уже стоит")


# ---------- админские команды ----------

@router.message(Command("collect"))
async def cmd_collect(message: Message, admin_ids: set[int],
                      collect_job: Callable[[], Awaitable[RunStats]]):
    if message.from_user.id not in admin_ids:
        return
    await message.answer("Запускаю сбор…")
    stats = await collect_job()
    await message.answer(f"Готово: {stats.summary()}")


@router.message(Command("stats"))
async def cmd_stats(message: Message, sessionmaker: async_sessionmaker, admin_ids: set[int]):
    if message.from_user.id not in admin_ids:
        return
    async with sessionmaker() as s:
        n_events = await repo.count_events(s)
        subs = await repo.active_subscribers(s)
    await message.answer(f"Событий в базе: {n_events}\nАктивных подписчиков: {len(subs)}")
