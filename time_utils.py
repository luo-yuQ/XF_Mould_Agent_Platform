"""Shared timezone helpers."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def format_china_time(value: datetime | None = None) -> str:
    """Format an instant as China Standard Time for server-rendered text."""
    timestamp = value or utc_now()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
