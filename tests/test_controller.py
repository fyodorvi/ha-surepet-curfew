"""Tests for FlapController with a fake API."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from api import PetDoorInfo
from controller import (
    SYNC_UNAVAILABLE_AFTER,
    DoorSettings,
    FlapController,
    PENDING_POLL_INTERVAL,
)
from state import (
    CurfewConfig,
    FlapSnapshot,
    LOCK_MODE_CURFEW,
    LOCK_MODE_LOCKED_IN,
    LOCK_MODE_UNLOCKED,
)

TZ = "Pacific/Auckland"


class FakeApi:
    def __init__(self, *, stale_reads: int = 0) -> None:
        self.mode = LOCK_MODE_CURFEW
        self.curfew_enabled = True
        self.online = True
        self.calls: list[tuple[str, Any]] = []
        self.last_curfew_times: tuple[str, str] | None = None
        self._stale_reads = stale_reads
        self._read_count = 0

    async def get_snapshot(
        self,
        device_id: int,
        *,
        household_id: int,
        now: datetime | None = None,
    ) -> FlapSnapshot:
        current = now or datetime.now(ZoneInfo(TZ))
        mode = self.mode
        if self._read_count < self._stale_reads:
            mode = LOCK_MODE_UNLOCKED
        self._read_count += 1

        curfew = CurfewConfig(
            enabled=self.curfew_enabled,
            lock_time="22:00",
            unlock_time="06:00",
        )
        from state import effective_locked

        locked, known = effective_locked(
            mode, curfew, now=current, curfew_locked=None
        )
        return FlapSnapshot(
            device_id=device_id,
            name="Test Door",
            product_id=3,
            online=self.online,
            mode=mode,
            curfew=curfew,
            effective_locked=locked,
            curfew_locked_known=known,
        )

    async def set_curfew(
        self,
        device_id: int,
        *,
        enabled: bool,
        lock_time: str,
        unlock_time: str,
    ) -> None:
        self.calls.append(("set_curfew", enabled))
        self.last_curfew_times = (lock_time, unlock_time)
        self.curfew_enabled = enabled
        if enabled:
            self.mode = LOCK_MODE_CURFEW

    async def unlock(self, device_id: int) -> None:
        self.calls.append(("unlock", None))
        self.mode = LOCK_MODE_UNLOCKED

    async def lock_in(self, device_id: int) -> None:
        self.calls.append(("lock_in", None))
        self.mode = LOCK_MODE_LOCKED_IN
        self.curfew_enabled = False


def _door() -> PetDoorInfo:
    return PetDoorInfo(
        device_id=1,
        name="Test Door",
        household_id=99,
        timezone=TZ,
    )


def _settings() -> DoorSettings:
    return DoorSettings(
        curfew_enabled=True,
        curfew_start="22:00",
        curfew_end="06:00",
        override_minutes=30,
    )


@pytest.fixture
def in_curfew_now() -> datetime:
    return datetime(2026, 9, 20, 23, 0, tzinfo=ZoneInfo(TZ))


@pytest.fixture
def outside_curfew_now() -> datetime:
    return datetime(2026, 9, 20, 12, 0, tzinfo=ZoneInfo(TZ))


@pytest.mark.asyncio
async def test_unlock_during_curfew_starts_override(in_curfew_now: datetime) -> None:
    api = FakeApi()
    controller = FlapController(api, now_func=lambda _tz: in_curfew_now)
    controller.register_door(_door(), _settings())

    await controller.unlock(1)

    assert controller.desired_effective_locked(1) is False
    assert ("set_curfew", False) in api.calls
    assert ("unlock", None) in api.calls
    assert controller.doors[1].override_until == in_curfew_now + timedelta(minutes=30)


@pytest.mark.asyncio
async def test_lock_during_override_cancels_override(in_curfew_now: datetime) -> None:
    api = FakeApi()
    api.curfew_enabled = False
    api.mode = LOCK_MODE_UNLOCKED
    controller = FlapController(api, now_func=lambda _tz: in_curfew_now)
    controller.register_door(_door(), _settings())
    controller.doors[1].override_until = in_curfew_now + timedelta(minutes=20)

    await controller.lock(1)

    assert controller.desired_effective_locked(1) is True
    assert controller.doors[1].override_until is None
    assert ("set_curfew", True) in api.calls


@pytest.mark.asyncio
async def test_lock_outside_curfew_exits_curfew(outside_curfew_now: datetime) -> None:
    api = FakeApi()
    controller = FlapController(api, now_func=lambda _tz: outside_curfew_now)
    controller.register_door(_door(), _settings())

    await controller.lock(1)

    assert controller.desired_effective_locked(1) is True
    assert controller.doors[1].lock_until_curfew is True
    assert ("lock_in", None) in api.calls


@pytest.mark.asyncio
async def test_override_expiry_restores_curfew(in_curfew_now: datetime) -> None:
    api = FakeApi()
    api.curfew_enabled = False
    api.mode = LOCK_MODE_UNLOCKED
    controller = FlapController(api, now_func=lambda _tz: in_curfew_now)
    controller.register_door(_door(), _settings())
    controller.doors[1].override_until = in_curfew_now - timedelta(minutes=1)

    await controller.refresh(1)

    assert controller.doors[1].override_until is None
    assert ("set_curfew", True) in api.calls


@pytest.mark.asyncio
async def test_curfew_switch_off_preserves_effective_state(
    outside_curfew_now: datetime,
) -> None:
    api = FakeApi()
    controller = FlapController(api, now_func=lambda _tz: outside_curfew_now)
    controller.register_door(_door(), _settings())
    await controller.refresh(1)

    await controller.set_curfew_enabled(1, False)

    assert controller.doors[1].settings.curfew_enabled is False
    assert controller.doors[1].manual_locked is False
    assert controller.desired_effective_locked(1) is False


@pytest.mark.asyncio
async def test_desired_locked_before_api_catches_up(outside_curfew_now: datetime) -> None:
    api = FakeApi(stale_reads=2)
    controller = FlapController(api, now_func=lambda _tz: outside_curfew_now)
    controller.register_door(_door(), _settings())

    await controller.lock(1)

    assert controller.desired_effective_locked(1) is True
    assert controller.doors[1].pending_since is not None


@pytest.mark.asyncio
async def test_pending_loop_retries_until_synced(outside_curfew_now: datetime) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        api.mode = LOCK_MODE_LOCKED_IN
        api.curfew_enabled = False

    api = FakeApi(stale_reads=3)
    controller = FlapController(
        api,
        now_func=lambda _tz: outside_curfew_now,
        sleep_func=fake_sleep,
        pending_poll_interval=5.0,
    )
    controller.register_door(_door(), DoorSettings(curfew_enabled=False))

    await controller.lock(1)
    assert controller.doors[1].pending_since is not None

    await asyncio.sleep(0)
    task = controller.doors[1]._pending_task
    if task:
        await task

    assert controller.doors[1].pending_since is None
    assert 5.0 in sleeps


@pytest.mark.asyncio
async def test_sync_failed_after_timeout(outside_curfew_now: datetime) -> None:
    api = FakeApi(stale_reads=100)
    start = outside_curfew_now

    def now_func(_tz: str) -> datetime:
        return start

    controller = FlapController(
        api,
        now_func=now_func,
        sync_unavailable_after=timedelta(minutes=5),
    )
    controller.register_door(_door(), _settings())
    controller.doors[1].settings.curfew_enabled = False
    controller.doors[1].manual_locked = True
    controller.doors[1].pending_since = start - timedelta(minutes=6)
    controller.doors[1].snapshot = await api.get_snapshot(1, household_id=99, now=start)

    assert controller.sync_failed(1) is True
    assert controller.is_available(1) is False


@pytest.mark.asyncio
async def test_sync_failed_false_while_still_retrying(outside_curfew_now: datetime) -> None:
    api = FakeApi(stale_reads=100)
    controller = FlapController(api, now_func=lambda _tz: outside_curfew_now)
    controller.register_door(_door(), _settings())
    controller.doors[1].settings.curfew_enabled = False
    controller.doors[1].manual_locked = True
    controller.doors[1].pending_since = outside_curfew_now
    controller.doors[1].snapshot = await api.get_snapshot(
        1, household_id=99, now=outside_curfew_now
    )

    assert controller.sync_failed(1) is False
    assert controller.is_available(1) is True


def test_desired_effective_locked_curfew_window(in_curfew_now: datetime) -> None:
    api = FakeApi()
    controller = FlapController(api, now_func=lambda _tz: in_curfew_now)
    controller.register_door(_door(), _settings())

    assert controller.desired_effective_locked(1) is True


@pytest.mark.asyncio
async def test_update_settings_pushes_new_times_to_api(
    outside_curfew_now: datetime,
) -> None:
    api = FakeApi()
    controller = FlapController(api, now_func=lambda _tz: outside_curfew_now)
    controller.register_door(_door(), _settings())
    await controller.refresh(1)

    new_settings = DoorSettings(
        curfew_enabled=True,
        curfew_start="21:00",
        curfew_end="07:00",
        override_minutes=30,
    )
    controller.update_settings(1, new_settings)
    await controller.push_curfew_schedule(1)

    assert api.last_curfew_times == ("21:00", "07:00")


@pytest.mark.asyncio
async def test_update_settings_reschedules_lock_until_curfew(
    outside_curfew_now: datetime,
) -> None:
    from schedule import seconds_until

    api = FakeApi()
    controller = FlapController(api, now_func=lambda _tz: outside_curfew_now)
    controller.register_door(_door(), _settings())

    controller.request_lock(1)
    assert controller.doors[1].lock_until_curfew is True
    old_delay = seconds_until(
        outside_curfew_now, "22:00", tz=ZoneInfo(TZ)
    )

    new_settings = DoorSettings(
        curfew_enabled=True,
        curfew_start="21:00",
        curfew_end="06:00",
        override_minutes=30,
    )
    controller.update_settings(1, new_settings)

    new_delay = seconds_until(
        outside_curfew_now, "21:00", tz=ZoneInfo(TZ)
    )
    assert new_delay < old_delay
    assert controller.doors[1]._transition_task is not None
