from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    type: Mapped[str] = mapped_column(String(20), index=True)
    audience: Mapped[list[str]] = mapped_column(JSON, default=list)
    cities: Mapped[list[str]] = mapped_column(JSON, default=list)
    organizer: Mapped[str | None] = mapped_column(String(200), index=True)
    # Все даты хранятся как naive UTC
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    time_known: Mapped[bool] = mapped_column(Boolean, default=False)
    url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(100))
    alt_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Subscriber(Base):
    __tablename__ = "subscribers"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    cities: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["spb", "msk", "online"])
    types: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["conference", "meetup", "hackathon", "other"]
    )
    audience: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["dev", "pm", "data"])
    only_yandex: Mapped[bool] = mapped_column(Boolean, default=False)
    digest: Mapped[str] = mapped_column(String(10), default="instant")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Reminder(Base):
    """Пользователь нажал «Напомнить» у события."""

    __tablename__ = "reminders"

    user_id: Mapped[int] = mapped_column(ForeignKey("subscribers.user_id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)


class Delivery(Base):
    """Какие события уже отправлены пользователю, чтобы не слать повторно."""

    __tablename__ = "deliveries"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
