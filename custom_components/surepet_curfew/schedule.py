"""Curfew schedule helpers."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def parse_hhmm(value: str) -> time:
    """Parse HH:MM into a time object."""
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


def format_hhmm(value: time) -> str:
    """Format a time object as HH:MM."""
    return value.strftime("%H:%M")


def in_curfew_window(now: datetime, start: str, end: str) -> bool:
    """Return True when now is inside the curfew lock window."""
    current = now.time().replace(second=0, microsecond=0)
    start_time = parse_hhmm(start)
    end_time = parse_hhmm(end)

    if start_time <= end_time:
        return start_time <= current < end_time
    return current >= start_time or current < end_time


def seconds_until(
    now: datetime,
    target_hhmm: str,
    *,
    tz: ZoneInfo | None = None,
) -> float:
    """Return seconds from now until the next occurrence of target HH:MM."""
    if tz is not None:
        now = now.astimezone(tz)

    target_time = parse_hhmm(target_hhmm)
    candidate = datetime.combine(now.date(), target_time, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=1)
    return (candidate - now).total_seconds()


def local_now(timezone_name: str) -> datetime:
    """Return current time in the household timezone."""
    return datetime.now(ZoneInfo(timezone_name))
