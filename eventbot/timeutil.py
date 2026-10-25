from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Текущее время как naive UTC — в таком виде даты лежат в БД."""
    return datetime.now(UTC).replace(tzinfo=None)


def local_to_utc(dt: datetime, tz: ZoneInfo) -> datetime:
    """naive local -> naive UTC"""
    return dt.replace(tzinfo=tz).astimezone(UTC).replace(tzinfo=None)


def utc_to_local(dt: datetime, tz: ZoneInfo) -> datetime:
    """naive UTC -> aware local"""
    return dt.replace(tzinfo=UTC).astimezone(tz)


def aware_to_utc(dt: datetime) -> datetime:
    """aware -> naive UTC (naive считаем уже UTC)"""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)
