"""Запросы к БД. Вся работа с SQLAlchemy собрана здесь."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from eventbot.db.models import Delivery, Event, Reminder, Subscriber
from eventbot.domain import EventData
from eventbot.pipeline.dedup import find_duplicate
from eventbot.timeutil import utcnow


# ---------- события ----------

async def save_events(session: AsyncSession, items: list[EventData]) -> list[Event]:
    """Сохраняет события с дедупликацией. Возвращает только действительно новые."""
    new: list[Event] = []
    for data in items:
        existing = await session.get(Event, data.id)
        if existing is None:
            candidates = await _dedup_candidates(session, data)
            existing = find_duplicate(data, candidates)
        if existing is not None:
            _merge(existing, data)
            continue
        ev = Event(
            id=data.id,
            title=data.title,
            type=data.type,
            audience=data.audience,
            cities=data.cities,
            organizer=data.organizer,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            time_known=data.time_known,
            url=data.url,
            source=data.source,
            alt_urls=[],
            description=data.description,
            first_seen_at=utcnow(),
            notified=False,
        )
        session.add(ev)
        await session.flush()
        new.append(ev)
    await session.commit()
    return new


async def _dedup_candidates(session: AsyncSession, data: EventData) -> list[Event]:
    if data.starts_at is None:
        stmt = select(Event).where(Event.starts_at.is_(None)).limit(500)
    else:
        lo, hi = data.starts_at - timedelta(days=2), data.starts_at + timedelta(days=2)
        stmt = select(Event).where(Event.starts_at.between(lo, hi))
    return list((await session.scalars(stmt)).all())


def _merge(ev: Event, data: EventData) -> None:
    """Дополняет существующее событие тем, чего в нём не было."""
    if data.url != ev.url and data.url not in (ev.alt_urls or []):
        ev.alt_urls = [*(ev.alt_urls or []), data.url]
    if not ev.time_known and data.time_known and data.starts_at:
        ev.starts_at, ev.time_known = data.starts_at, True
    if ev.starts_at is None and data.starts_at:
        ev.starts_at = data.starts_at
    if ev.ends_at is None and data.ends_at:
        ev.ends_at = data.ends_at
    if not ev.cities and data.cities:
        ev.cities = data.cities
    elif data.cities:
        ev.cities = sorted(set(ev.cities) | set(data.cities))
    if not ev.audience and data.audience:
        ev.audience = data.audience
    if len(data.description) > len(ev.description or ""):
        ev.description = data.description
    if ev.type == "other" and data.type != "other":
        ev.type = data.type
    if not ev.organizer and data.organizer:
        ev.organizer = data.organizer


async def upcoming(session: AsyncSession, now: datetime, days: int = 60) -> list[Event]:
    """Будущие события (и события без даты, найденные за последний месяц)."""
    stmt = (
        select(Event)
        .where(
            or_(
                Event.starts_at.between(now - timedelta(hours=12), now + timedelta(days=days)),
                and_(Event.starts_at.is_(None), Event.first_seen_at >= now - timedelta(days=30)),
            )
        )
        .order_by(Event.starts_at.is_(None), Event.starts_at)
    )
    return list((await session.scalars(stmt)).all())


async def unnotified(session: AsyncSession) -> list[Event]:
    return list((await session.scalars(select(Event).where(Event.notified.is_(False)))).all())


async def mark_notified(session: AsyncSession, ids: list[str]) -> None:
    if ids:
        await session.execute(update(Event).where(Event.id.in_(ids)).values(notified=True))
        await session.commit()


async def seen_since(session: AsyncSession, since: datetime) -> list[Event]:
    stmt = select(Event).where(Event.first_seen_at >= since).order_by(Event.starts_at)
    return list((await session.scalars(stmt)).all())


async def count_events(session: AsyncSession) -> int:
    return len((await session.scalars(select(Event.id))).all())


# ---------- подписчики ----------

async def get_or_create_subscriber(session: AsyncSession, user_id: int, chat_id: int) -> tuple[Subscriber, bool]:
    sub = await session.get(Subscriber, user_id)
    if sub:
        if not sub.active:
            sub.active = True
            await session.commit()
        return sub, False
    sub = Subscriber(
        user_id=user_id,
        chat_id=chat_id,
        cities=["spb", "msk", "online"],
        types=["conference", "meetup", "hackathon", "other"],
        audience=["dev", "pm", "data"],
        only_yandex=False,
        digest="instant",
        active=True,
    )
    session.add(sub)
    await session.commit()
    return sub, True


async def active_subscribers(session: AsyncSession, digest: str | None = None) -> list[Subscriber]:
    stmt = select(Subscriber).where(Subscriber.active.is_(True))
    if digest:
        stmt = stmt.where(Subscriber.digest == digest)
    return list((await session.scalars(stmt)).all())


# ---------- доставки и напоминания ----------

async def delivered_ids(session: AsyncSession, user_id: int) -> set[str]:
    rows = await session.scalars(select(Delivery.event_id).where(Delivery.user_id == user_id))
    return set(rows.all())


async def record_deliveries(session: AsyncSession, user_id: int, event_ids: list[str]) -> None:
    for eid in event_ids:
        await session.merge(Delivery(user_id=user_id, event_id=eid))
    await session.commit()


async def add_reminder(session: AsyncSession, user_id: int, event_id: str) -> bool:
    if await session.get(Reminder, (user_id, event_id)):
        return False
    session.add(Reminder(user_id=user_id, event_id=event_id, sent=False))
    await session.commit()
    return True


async def due_reminders(session: AsyncSession, now: datetime, ahead: timedelta) -> list[tuple[Reminder, Event, Subscriber]]:
    stmt = (
        select(Reminder, Event, Subscriber)
        .join(Event, Event.id == Reminder.event_id)
        .join(Subscriber, Subscriber.user_id == Reminder.user_id)
        .where(
            Reminder.sent.is_(False),
            Subscriber.active.is_(True),
            Event.starts_at.is_not(None),
            Event.starts_at.between(now, now + ahead),
        )
    )
    return [tuple(r) for r in (await session.execute(stmt)).all()]
