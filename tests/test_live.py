"""Live tests against the real Pet Door Connect."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiohttp
import pytest

from api import SurePetApi
from controller import DoorSettings, FlapController
from schedule import in_curfew_window
from state import LOCK_MODE_CURFEW, LOCK_MODE_LOCKED_IN, LOCK_MODE_UNLOCKED

pytestmark = pytest.mark.live


def _load_credentials(path: Path) -> tuple[str, str]:
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    return lines[0], lines[1]


@dataclass
class DoorBackup:
    enabled: bool
    lock_time: str
    unlock_time: str
    mode: int


@pytest.fixture
async def live_api(credentials_path: Path, has_credentials: bool):
    if not has_credentials:
        pytest.skip("No .credentials file")
    email, password = _load_credentials(credentials_path)
    session = aiohttp.ClientSession()
    api = SurePetApi(email, password, session=session)
    await api.connect()
    doors = await api.list_pet_doors()
    if not doors:
        await api.close()
        pytest.skip("No Pet Door Connect in account")
    yield api, doors[0]
    await api.close()


@pytest.fixture
async def door_backup(live_api):
    api, door = live_api
    snap = await api.get_snapshot(door.device_id, household_id=door.household_id)
    backup = DoorBackup(
        enabled=snap.curfew.enabled,
        lock_time=snap.curfew.lock_time,
        unlock_time=snap.curfew.unlock_time,
        mode=snap.mode,
    )
    yield backup
    if backup.enabled:
        await api.set_curfew(
            door.device_id,
            enabled=True,
            lock_time=backup.lock_time,
            unlock_time=backup.unlock_time,
        )
    else:
        await api.set_curfew(
            door.device_id,
            enabled=False,
            lock_time=backup.lock_time,
            unlock_time=backup.unlock_time,
        )
        if backup.mode == LOCK_MODE_LOCKED_IN:
            await api.lock_in(door.device_id)
        elif backup.mode == LOCK_MODE_UNLOCKED:
            await api.unlock(door.device_id)


@pytest.mark.asyncio
async def test_live_discover_pet_door(live_api) -> None:
    api, door = live_api
    snap = await api.get_snapshot(door.device_id, household_id=door.household_id)
    assert snap.product_id == 3
    assert snap.name


@pytest.mark.asyncio
async def test_live_lock_and_unlock(live_api, door_backup) -> None:
    api, door = live_api
    await api.lock_in(door.device_id)
    snap = await api.get_snapshot(door.device_id, household_id=door.household_id)
    assert snap.mode == LOCK_MODE_LOCKED_IN

    await api.unlock(door.device_id)
    snap = await api.get_snapshot(door.device_id, household_id=door.household_id)
    assert snap.mode == LOCK_MODE_UNLOCKED


@pytest.mark.asyncio
async def test_live_set_curfew_dict(live_api, door_backup) -> None:
    api, door = live_api
    await api.set_curfew(
        door.device_id,
        enabled=True,
        lock_time="23:59",
        unlock_time="00:01",
    )
    snap = await api.get_snapshot(door.device_id, household_id=door.household_id)
    assert snap.curfew.enabled is True
    assert snap.curfew.lock_time == "23:59"


@pytest.mark.asyncio
async def test_live_lock_cancels_override(live_api, door_backup) -> None:
    api, door = live_api
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(door.timezone))
    if not in_curfew_window(now, door_backup.lock_time, door_backup.unlock_time):
        pytest.skip("Not currently in curfew window")

    controller = FlapController(api, now_func=lambda _tz: now)
    controller.register_door(
        door,
        DoorSettings(
            curfew_enabled=True,
            curfew_start=door_backup.lock_time,
            curfew_end=door_backup.unlock_time,
            override_minutes=5,
        ),
    )

    await controller.unlock(door.device_id)
    assert controller.doors[door.device_id].override_until is not None

    await controller.lock(door.device_id)
    assert controller.doors[door.device_id].override_until is None

    snap = await api.get_snapshot(door.device_id, household_id=door.household_id)
    assert snap.curfew.enabled is True or snap.mode == LOCK_MODE_CURFEW
