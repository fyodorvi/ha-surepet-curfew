"""Tests for state parsing."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from state import (
    LOCK_MODE_CURFEW,
    LOCK_MODE_LOCKED_IN,
    LOCK_MODE_UNLOCKED,
    effective_locked,
    parse_curfew_config,
    snapshot_from_raw,
)


def test_parse_curfew_dict() -> None:
    curfew = parse_curfew_config(
        {"enabled": True, "lock_time": "22:00", "unlock_time": "06:00"}
    )
    assert curfew.enabled is True
    assert curfew.lock_time == "22:00"


def test_effective_locked_mode_4_with_flag() -> None:
    curfew = parse_curfew_config(
        {"enabled": True, "lock_time": "22:00", "unlock_time": "06:00"}
    )
    locked, known = effective_locked(
        LOCK_MODE_CURFEW, curfew, now=datetime.now(), curfew_locked=True
    )
    assert locked is True
    assert known is True


def test_effective_locked_mode_4_computed_overnight(pet_door_unlocked: dict) -> None:
    pet_door_unlocked["status"]["locking"]["mode"] = LOCK_MODE_CURFEW
    pet_door_unlocked["control"]["curfew"]["enabled"] = True
    now = datetime(2026, 9, 20, 23, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    snap = snapshot_from_raw(
        pet_door_unlocked, now=now, timezone_name="Pacific/Auckland"
    )
    assert snap.effective_locked is True
    assert snap.curfew_locked_known is False


def test_snapshot_unlocked(pet_door_unlocked: dict) -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    snap = snapshot_from_raw(
        pet_door_unlocked, now=now, timezone_name="Pacific/Auckland"
    )
    assert snap.mode == LOCK_MODE_UNLOCKED
    assert snap.effective_locked is False


def test_snapshot_locked_in(pet_door_unlocked: dict) -> None:
    pet_door_unlocked["status"]["locking"]["mode"] = LOCK_MODE_LOCKED_IN
    now = datetime(2026, 9, 20, 12, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    snap = snapshot_from_raw(
        pet_door_unlocked, now=now, timezone_name="Pacific/Auckland"
    )
    assert snap.effective_locked is True
