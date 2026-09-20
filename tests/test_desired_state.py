"""Tests for desired vs observed lock state."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from api import PetDoorInfo
from controller import DoorSettings, FlapController
from state import (
    CurfewConfig,
    FlapSnapshot,
    LOCK_MODE_LOCKED_IN,
    LOCK_MODE_UNLOCKED,
)
from ui_state import entity_is_locked, observed_is_locked

TZ = "Pacific/Auckland"
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=ZoneInfo(TZ))


def _snapshot(mode: int, locked: bool, online: bool = True) -> FlapSnapshot:
    curfew = CurfewConfig(enabled=True, lock_time="22:00", unlock_time="06:00")
    return FlapSnapshot(
        device_id=1,
        name="Test Door",
        product_id=3,
        online=online,
        mode=mode,
        curfew=curfew,
        effective_locked=locked,
        curfew_locked_known=True,
    )


def _door() -> PetDoorInfo:
    return PetDoorInfo(1, "Test", 99, TZ)


class StaleApi:
    """API that returns stale unlocked reads until lock_in is called."""

    def __init__(self) -> None:
        self.mode = LOCK_MODE_UNLOCKED
        self.calls: list[str] = []

    async def get_snapshot(self, device_id, *, household_id, now=None):
        locked = self.mode == LOCK_MODE_LOCKED_IN
        return _snapshot(self.mode, locked)

    async def lock_in(self, device_id):
        self.calls.append("lock_in")
        self.mode = LOCK_MODE_LOCKED_IN

    async def set_curfew(self, *args, **kwargs):
        self.calls.append("set_curfew")

    async def unlock(self, device_id):
        self.calls.append("unlock")
        self.mode = LOCK_MODE_UNLOCKED


class AlwaysStaleUnlockedApi:
    """API that keeps reporting unlocked even after lock_in (lagging door)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_snapshot(self, device_id, *, household_id, now=None):
        return _snapshot(LOCK_MODE_UNLOCKED, False)

    async def lock_in(self, device_id):
        self.calls.append("lock_in")

    async def set_curfew(self, *args, **kwargs):
        self.calls.append("set_curfew")

    async def unlock(self, device_id):
        self.calls.append("unlock")


@pytest.mark.asyncio
async def test_sync_clears_pending_when_observed_matches() -> None:
    api = StaleApi()
    controller = FlapController(api, now_func=lambda _tz: NOW)
    controller.register_door(_door(), DoorSettings(curfew_enabled=False))
    controller.doors[1].manual_locked = True
    controller.doors[1].pending_since = NOW

    await controller.refresh(1)

    assert controller.doors[1].pending_since is None
    assert controller.is_available(1) is True


def test_request_lock_updates_desired_without_api() -> None:
    api = StaleApi()
    controller = FlapController(api, now_func=lambda _tz: NOW)
    controller.register_door(_door(), DoorSettings(curfew_enabled=False))

    controller.request_lock(1)

    assert controller.desired_effective_locked(1) is True
    assert controller.doors[1].pending_since == NOW
    assert api.calls == []


def test_request_unlock_updates_desired_without_api() -> None:
    api = StaleApi()
    controller = FlapController(api, now_func=lambda _tz: NOW)
    controller.register_door(_door(), DoorSettings(curfew_enabled=False))
    controller.doors[1].manual_locked = True
    controller.doors[1].snapshot = _snapshot(LOCK_MODE_LOCKED_IN, True)

    controller.request_unlock(1)

    assert controller.desired_effective_locked(1) is False
    assert controller.doors[1].pending_since == NOW
    assert api.calls == []


@pytest.mark.asyncio
async def test_poll_does_not_revert_desired_after_request_lock() -> None:
    api = AlwaysStaleUnlockedApi()
    controller = FlapController(api, now_func=lambda _tz: NOW)
    controller.register_door(_door(), DoorSettings())
    controller.doors[1].snapshot = _snapshot(LOCK_MODE_UNLOCKED, False)

    controller.request_lock(1)

    assert controller.desired_effective_locked(1) is True
    assert controller.doors[1].lock_until_curfew is True

    await controller.refresh(1)

    assert controller.desired_effective_locked(1) is True
    assert controller.doors[1].lock_until_curfew is True
    assert controller.doors[1].snapshot is not None
    assert observed_is_locked(controller.doors[1].snapshot) is False
    assert "lock_in" in api.calls


def test_ui_mapping_follows_desired_not_observed() -> None:
    api = StaleApi()
    controller = FlapController(api, now_func=lambda _tz: NOW)
    controller.register_door(_door(), DoorSettings(curfew_enabled=False))
    controller.doors[1].snapshot = _snapshot(LOCK_MODE_UNLOCKED, False)

    controller.request_lock(1)

    desired = controller.desired_effective_locked(1)
    observed = observed_is_locked(controller.doors[1].snapshot)
    ui_locked = entity_is_locked(desired)

    assert desired is True
    assert observed is False
    assert ui_locked is True
    assert ui_locked == desired
    assert ui_locked != observed


@pytest.mark.asyncio
async def test_reconcile_commands_door_after_optimistic_lock() -> None:
    api = StaleApi()
    controller = FlapController(api, now_func=lambda _tz: NOW)
    controller.register_door(_door(), DoorSettings(curfew_enabled=False))
    controller.doors[1].snapshot = _snapshot(LOCK_MODE_UNLOCKED, False)

    controller.request_lock(1)
    assert api.calls == []
    assert controller.desired_effective_locked(1) is True

    await controller.reconcile(1)

    assert "lock_in" in api.calls
    assert controller.desired_effective_locked(1) is True
    assert controller.doors[1].snapshot is not None
    assert controller.doors[1].snapshot.effective_locked is True


@pytest.mark.asyncio
async def test_begin_sync_starts_pending_when_stale() -> None:
    controller = FlapController(
        AlwaysStaleUnlockedApi(),
        now_func=lambda _tz: NOW,
        pending_poll_interval=0.01,
        sync_unavailable_after=timedelta(minutes=5),
    )
    controller.register_door(_door(), DoorSettings(curfew_enabled=False))

    await controller.lock(1)

    assert controller.desired_effective_locked(1) is True
    assert controller.doors[1].pending_since is not None
