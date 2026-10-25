from datetime import timedelta
from types import SimpleNamespace

from eventbot.bot.formatting import format_event, format_when
from eventbot.bot.ics import build_ics
from eventbot.bot.notifier import Notifier
from eventbot.db import repo
from eventbot.db.models import Event
from eventbot.domain import RawEvent
from eventbot.filters import matches
from eventbot.pipeline.dedup import similarity
from eventbot.pipeline.normalize import to_event_data
from eventbot.timeutil import utcnow


def _raw(title, days=10, hour=None, url=None, city="Москва", source="test"):
    start = (utcnow() + timedelta(days=days)).replace(hour=hour or 21, minute=0, second=0, microsecond=0)
    return RawEvent(title=title, url=url or f"https://ex.com/{abs(hash(title))}", source=source,
                    starts_at=start, time_known=hour is not None, organizer="Яндекс", city_hint=city)


def test_similarity():
    assert similarity("Data Driven 2026", "«Data Driven»") >= 88
    assert similarity("deep tech night", "deep tech night: программа готова") >= 88
    assert similarity("Data", "Data Driven") < 88
    assert similarity("Frontend Meetup", "Backend Meetup") < 88


async def test_save_dedup_and_merge(sm):
    a = to_event_data(_raw("deep tech night", days=5))
    b = to_event_data(_raw("deep tech night: программа готова", days=5, hour=15, source="other"))
    c = to_event_data(_raw("Frontend Meetup", days=5))
    async with sm() as s:
        new1 = await repo.save_events(s, [a, c])
        new2 = await repo.save_events(s, [b, a])
        assert len(new1) == 2 and new2 == []
        ev = await s.get(Event, a.id)
        assert ev.time_known and ev.starts_at.hour == 15  # уточнённое время подтянулось
        assert b.url in ev.alt_urls


def test_matches():
    sub = SimpleNamespace(types=["meetup"], cities=["spb"], audience=["pm"], only_yandex=False)
    ev = SimpleNamespace(type="meetup", cities=["spb", "online"], audience=["pm", "dev"], organizer="X")
    assert matches(sub, ev)
    assert not matches(sub, SimpleNamespace(**{**ev.__dict__, "cities": ["msk"]}))
    assert matches(sub, SimpleNamespace(**{**ev.__dict__, "cities": [], "audience": []}))
    sub.only_yandex = True
    assert not matches(sub, ev)


def _event(**kw):
    base = dict(id="x" * 40, title="Я про бэкенд", type="conference", audience=["dev"], cities=["msk", "online"],
                organizer="Яндекс", starts_at=None, ends_at=None, time_known=False, url="https://e.ru/a?b=1&c=2", source="t", alt_urls=[],
                description="Доклады; кофе, нетворкинг")
    base.update(kw)
    return Event(**base)


def test_formatting_and_ics(tz):
    from datetime import datetime
    ev = _event(starts_at=datetime(2026, 10, 3, 8, 0), time_known=True)
    assert format_when(ev, tz) == "3 октября 2026, 11:00"
    text = format_event(ev, tz)
    assert "Москва, Онлайн" in text and "&amp;c=2" in text
    ics = build_ics(ev, tz)
    assert "DTSTART:20261003T080000Z" in ics and "DTEND:20261003T100000Z" in ics
    assert "Доклады\\; кофе\\, нетворкинг" in ics

    multi = _event(starts_at=datetime(2026, 9, 11, 21), ends_at=datetime(2026, 9, 17, 21))
    assert format_when(multi, tz) == "12–18 сентября 2026"
    assert "DTSTART;VALUE=DATE:20260912" in build_ics(multi, tz)
    assert "DTEND;VALUE=DATE:20260919" in build_ics(multi, tz)
    assert build_ics(_event(), tz) is None


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


async def test_notify_new_respects_filters_and_dedup(sm, tz):
    async with sm() as s:
        await repo.get_or_create_subscriber(s, 1, 1)  # все фильтры по умолчанию
        spb_only, _ = await repo.get_or_create_subscriber(s, 2, 2)
        spb_only.cities = ["spb"]
        await s.commit()
        await repo.save_events(s, [to_event_data(_raw("Frontend Meetup", city="Москва")),
                                   to_event_data(_raw("Хакатон Питер", city="Санкт-Петербург"))])
    bot = FakeBot()
    n = Notifier(bot, sm, tz)
    await n.notify_new()
    to_user = lambda uid: [t for c, t in bot.sent if c == uid]
    assert len(to_user(1)) == 2
    assert len(to_user(2)) == 1 and "Хакатон Питер" in to_user(2)[0]

    bot.sent.clear()
    await n.notify_new()  # повторно ничего не шлём
    assert bot.sent == []


async def test_reminders(sm, tz):
    async with sm() as s:
        await repo.get_or_create_subscriber(s, 1, 1)
        [ev] = await repo.save_events(s, [to_event_data(_raw("Скоро митап", days=0, hour=23))])
        ev.starts_at = utcnow() + timedelta(hours=5)
        await s.commit()
        assert await repo.add_reminder(s, 1, ev.id)
        assert not await repo.add_reminder(s, 1, ev.id)
    bot = FakeBot()
    n = Notifier(bot, sm, tz)
    await n.reminders()
    await n.reminders()
    assert len(bot.sent) == 1 and "Напоминание" in bot.sent[0][1]
