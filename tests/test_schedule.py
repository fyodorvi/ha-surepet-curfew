"""Tests for schedule helpers."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from schedule import format_hhmm, in_curfew_window, normalize_hhmm, parse_hhmm, seconds_until


def test_overnight_curfew_inside_window() -> None:
    now = datetime(2026, 9, 20, 23, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    assert in_curfew_window(now, "22:00", "06:00") is True


def test_overnight_curfew_outside_window() -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    assert in_curfew_window(now, "22:00", "06:00") is False


def test_same_day_curfew() -> None:
    now = datetime(2026, 9, 20, 13, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    assert in_curfew_window(now, "12:00", "18:00") is True
    assert in_curfew_window(now, "18:00", "22:00") is False


def test_seconds_until_next_occurrence() -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    assert seconds_until(now, "22:00", tz=ZoneInfo("Pacific/Auckland")) == 10 * 3600


def test_format_hhmm_round_trip() -> None:
    value = time(hour=21, minute=30)
    assert format_hhmm(value) == "21:30"
    assert parse_hhmm(format_hhmm(value)) == value


def test_normalize_hhmm_strips_seconds() -> None:
    assert normalize_hhmm("22:00:00") == "22:00"
    assert normalize_hhmm("06:00") == "06:00"
