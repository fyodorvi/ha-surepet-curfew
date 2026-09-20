"""Desired-state controller for Pet Door Connect."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Awaitable

from surepy.enums import LockState

try:
    from .api import PetDoorInfo, SurePetApi
    from .schedule import in_curfew_window, local_now, normalize_hhmm, seconds_until
    from .state import FlapSnapshot, LOCK_MODE_CURFEW
except ImportError:
    from api import PetDoorInfo, SurePetApi
    from schedule import in_curfew_window, local_now, normalize_hhmm, seconds_until
    from state import FlapSnapshot, LOCK_MODE_CURFEW

_LOGGER = logging.getLogger(__name__)

PENDING_POLL_INTERVAL = 15.0
SYNC_UNAVAILABLE_AFTER = timedelta(minutes=5)

SleepFunc = Callable[[float], Awaitable[None]]
NotifyFunc = Callable[[], None]


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


@dataclass
class DoorSettings:
    """User-configured curfew settings."""

    curfew_enabled: bool = True
    curfew_start: str = "22:00"
    curfew_end: str = "06:00"
    override_minutes: int = 30


@dataclass
class DoorRuntime:
    """Per-door runtime state."""

    info: PetDoorInfo
    settings: DoorSettings = field(default_factory=DoorSettings)
    override_until: datetime | None = None
    lock_until_curfew: bool = False
    manual_locked: bool | None = None
    snapshot: FlapSnapshot | None = None
    pending_since: datetime | None = None
    last_successful_sync: datetime | None = None
    _transition_task: asyncio.Task[None] | None = None
    _pending_task: asyncio.Task[None] | None = None


class FlapController:
    """Maintain desired Pet Door state with timers and reconcile."""

    def __init__(
        self,
        api: SurePetApi,
        *,
        sleep_func: SleepFunc = _default_sleep,
        now_func: Callable[[str], datetime] | None = None,
        on_change: NotifyFunc | None = None,
        pending_poll_interval: float = PENDING_POLL_INTERVAL,
        sync_unavailable_after: timedelta = SYNC_UNAVAILABLE_AFTER,
    ) -> None:
        self._api = api
        self._sleep = sleep_func
        self._now = now_func or local_now
        self._on_change = on_change
        self._pending_poll_interval = pending_poll_interval
        self._sync_unavailable_after = sync_unavailable_after
        self._doors: dict[int, DoorRuntime] = {}

    @property
    def doors(self) -> dict[int, DoorRuntime]:
        return self._doors

    def register_door(self, info: PetDoorInfo, settings: DoorSettings) -> None:
        self._doors[info.device_id] = DoorRuntime(info=info, settings=settings)

    def update_settings(self, device_id: int, settings: DoorSettings) -> None:
        door = self._doors[device_id]
        door.settings = settings
        if not settings.curfew_enabled:
            door.override_until = None
            door.lock_until_curfew = False
            self._cancel_transition_timer(door)
        else:
            self._schedule_next_transition(door)

    def desired_effective_locked(self, device_id: int) -> bool:
        """Return the effective lock state we intend to maintain."""
        return self._desired_effective_locked(self._doors[device_id])

    def is_available(self, device_id: int) -> bool:
        """Return False after sustained failure to reach desired state."""
        return not self._sync_failed(self._doors[device_id])

    def sync_failed(self, device_id: int) -> bool:
        """Return True when reconcile has been failing long enough to surface."""
        return self._sync_failed(self._doors[device_id])

    async def refresh(self, device_id: int) -> FlapSnapshot:
        """Poll API and reconcile to desired state."""
        return await self._sync_once(device_id)

    def request_lock(self, device_id: int) -> None:
        """Apply locked intent immediately without waiting on the API."""
        door = self._doors[device_id]
        now = self._now(door.info.timezone)

        if not door.settings.curfew_enabled:
            door.manual_locked = True
            door.override_until = None
            door.lock_until_curfew = False
            self._cancel_transition_timer(door)
        elif door.override_until and now < door.override_until:
            door.override_until = None
            door.lock_until_curfew = False
        elif in_curfew_window(now, door.settings.curfew_start, door.settings.curfew_end):
            door.override_until = None
            door.lock_until_curfew = False
        else:
            door.lock_until_curfew = True
            door.override_until = None

        door.pending_since = now
        self._schedule_next_transition(door)

    def request_unlock(self, device_id: int) -> None:
        """Apply unlocked intent immediately without waiting on the API."""
        door = self._doors[device_id]
        now = self._now(door.info.timezone)

        if not door.settings.curfew_enabled:
            door.manual_locked = False
            door.override_until = None
            door.lock_until_curfew = False
            self._cancel_transition_timer(door)
        elif in_curfew_window(now, door.settings.curfew_start, door.settings.curfew_end):
            door.override_until = now + timedelta(minutes=door.settings.override_minutes)
            door.lock_until_curfew = False
        else:
            door.lock_until_curfew = False
            door.override_until = None

        door.pending_since = now
        self._schedule_next_transition(door)

    def request_curfew_enabled(self, device_id: int, enabled: bool) -> None:
        """Apply curfew on/off intent immediately without waiting on the API."""
        door = self._doors[device_id]
        now = self._now(door.info.timezone)
        door.settings.curfew_enabled = enabled
        if not enabled:
            door.override_until = None
            door.lock_until_curfew = False
            if door.manual_locked is None:
                door.manual_locked = (
                    door.snapshot.effective_locked if door.snapshot else True
                )
            self._cancel_transition_timer(door)
        else:
            door.manual_locked = None

        door.pending_since = now
        if enabled:
            self._schedule_next_transition(door)

    async def reconcile(self, device_id: int) -> None:
        """Push desired state to the API and start fast retry polling if needed."""
        try:
            await self._begin_sync(device_id)
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Reconcile failed for %s", self._doors[device_id].info.name
            )
            self._schedule_pending_loop(device_id)
            self._notify_change()

    async def push_curfew_schedule(self, device_id: int) -> None:
        """Push updated curfew times to the API even when otherwise synced."""
        door = self._doors[device_id]
        now = self._now(door.info.timezone)
        if door.pending_since is None:
            door.pending_since = now
        try:
            if door.settings.curfew_enabled:
                if door.override_until and now < door.override_until:
                    await self._set_curfew(
                        door,
                        reason="schedule_push_override",
                        enabled=False,
                        lock_time=door.settings.curfew_start,
                        unlock_time=door.settings.curfew_end,
                    )
                elif door.lock_until_curfew:
                    await self._set_curfew(
                        door,
                        reason="schedule_push_lock_until_curfew",
                        enabled=False,
                        lock_time=door.settings.curfew_start,
                        unlock_time=door.settings.curfew_end,
                    )
                else:
                    await self._apply_native_curfew(door, reason="schedule_push")

            snapshot = await self._api.get_snapshot(
                door.info.device_id,
                household_id=door.info.household_id,
                now=now,
            )
            door.snapshot = snapshot
            if self._is_synced(door):
                door.pending_since = None
                door.last_successful_sync = now
            self._schedule_pending_loop(device_id)
            self._notify_change()
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Curfew schedule push failed for %s", door.info.name
            )
            self._schedule_pending_loop(device_id)
            self._notify_change()

    async def lock(self, device_id: int) -> None:
        """Request locked state and sync immediately."""
        self.request_lock(device_id)
        await self.reconcile(device_id)

    async def unlock(self, device_id: int) -> None:
        """Request unlocked state and sync immediately."""
        self.request_unlock(device_id)
        await self.reconcile(device_id)

    async def set_curfew_enabled(self, device_id: int, enabled: bool) -> None:
        self.request_curfew_enabled(device_id, enabled)
        await self.reconcile(device_id)

    async def shutdown(self) -> None:
        for door in self._doors.values():
            self._cancel_transition_timer(door)
            self._cancel_pending_loop(door)

    def _desired_effective_locked(self, door: DoorRuntime) -> bool:
        now = self._now(door.info.timezone)
        if not door.settings.curfew_enabled:
            return bool(door.manual_locked)
        if door.override_until and now < door.override_until:
            return False
        if door.lock_until_curfew:
            return True
        return in_curfew_window(
            now, door.settings.curfew_start, door.settings.curfew_end
        )

    def _is_native_curfew_mode(self, door: DoorRuntime) -> bool:
        """Return True when the door should run native curfew scheduling."""
        if not door.settings.curfew_enabled:
            return False
        now = self._now(door.info.timezone)
        if door.override_until and now < door.override_until:
            return False
        if door.lock_until_curfew:
            return False
        return True

    def _native_curfew_configured(self, door: DoorRuntime, snap: FlapSnapshot) -> bool:
        """Return True when the device already has the expected native curfew."""
        return (
            snap.curfew.enabled
            and snap.mode == LOCK_MODE_CURFEW
            and normalize_hhmm(snap.curfew.lock_time)
            == normalize_hhmm(door.settings.curfew_start)
            and normalize_hhmm(snap.curfew.unlock_time)
            == normalize_hhmm(door.settings.curfew_end)
        )

    def _is_synced(self, door: DoorRuntime) -> bool:
        snap = door.snapshot
        if snap is None or not snap.online:
            return False

        if self._is_native_curfew_mode(door):
            # Native curfew owns lock/unlock; do not re-PUT on stale lock flags.
            return self._native_curfew_configured(door, snap)

        desired_locked = self._desired_effective_locked(door)
        if snap.effective_locked != desired_locked:
            return False

        now = self._now(door.info.timezone)

        if not door.settings.curfew_enabled:
            return not snap.curfew.enabled

        if door.override_until and now < door.override_until:
            return not snap.curfew.enabled

        if door.lock_until_curfew:
            return not snap.curfew.enabled

        return False

    def _sync_failed(self, door: DoorRuntime) -> bool:
        if door.pending_since is None:
            return False
        now = self._now(door.info.timezone)
        if now - door.pending_since < self._sync_unavailable_after:
            return False
        return not self._is_synced(door)

    async def _begin_sync(self, device_id: int) -> None:
        door = self._doors[device_id]
        now = self._now(door.info.timezone)
        if door.pending_since is None:
            door.pending_since = now
        await self._sync_once(device_id)
        self._schedule_pending_loop(device_id)
        self._notify_change()

    async def _sync_once(self, device_id: int) -> FlapSnapshot:
        door = self._doors[device_id]
        now = self._now(door.info.timezone)

        if door.override_until and now >= door.override_until:
            door.override_until = None

        snapshot = await self._api.get_snapshot(
            device_id,
            household_id=door.info.household_id,
            now=now,
        )
        door.snapshot = snapshot
        await self._handle_external_changes(door, snapshot)

        if not self._is_synced(door):
            await self._apply_desired_state(door)
            snapshot = await self._api.get_snapshot(
                device_id,
                household_id=door.info.household_id,
                now=now,
            )
            door.snapshot = snapshot

        if self._is_synced(door):
            door.pending_since = None
            door.last_successful_sync = now
        elif door.pending_since is None:
            door.pending_since = now

        return door.snapshot

    def _log_api_write(self, door: DoorRuntime, action: str, reason: str) -> None:
        snap = door.snapshot
        _LOGGER.info(
            "%s: %s reason=%s mode=%s effective_locked=%s curfew_enabled=%s",
            door.info.name,
            action,
            reason,
            snap.mode if snap else None,
            snap.effective_locked if snap else None,
            snap.curfew.enabled if snap else None,
        )

    async def _set_curfew(
        self,
        door: DoorRuntime,
        *,
        reason: str,
        enabled: bool,
        lock_time: str,
        unlock_time: str,
    ) -> None:
        self._log_api_write(
            door,
            f"set_curfew(enabled={enabled}, lock={lock_time}, unlock={unlock_time})",
            reason,
        )
        await self._api.set_curfew(
            door.info.device_id,
            enabled=enabled,
            lock_time=lock_time,
            unlock_time=unlock_time,
        )

    async def _unlock(self, door: DoorRuntime, *, reason: str) -> None:
        self._log_api_write(door, "unlock", reason)
        await self._api.unlock(door.info.device_id)

    async def _lock_in(self, door: DoorRuntime, *, reason: str) -> None:
        self._log_api_write(door, "lock_in", reason)
        await self._api.lock_in(door.info.device_id)

    async def _apply_desired_state(self, door: DoorRuntime) -> None:
        """Push API commands needed to reach desired state."""
        now = self._now(door.info.timezone)

        if not door.settings.curfew_enabled:
            if door.snapshot and door.snapshot.curfew.enabled:
                await self._set_curfew(
                    door,
                    reason="manual_mode_disable_curfew",
                    enabled=False,
                    lock_time=door.settings.curfew_start,
                    unlock_time=door.settings.curfew_end,
                )
            if door.manual_locked:
                await self._lock_in(door, reason="manual_mode_lock")
            else:
                await self._unlock(door, reason="manual_mode_unlock")
            return

        if door.override_until:
            if now < door.override_until:
                await self._set_curfew(
                    door,
                    reason="override_disable_curfew",
                    enabled=False,
                    lock_time=door.settings.curfew_start,
                    unlock_time=door.settings.curfew_end,
                )
                await self._unlock(door, reason="override_unlock")
                return
            door.override_until = None

        if door.lock_until_curfew:
            if in_curfew_window(
                now, door.settings.curfew_start, door.settings.curfew_end
            ):
                door.lock_until_curfew = False
                await self._apply_native_curfew(door, reason="lock_until_curfew_restore")
            else:
                await self._set_curfew(
                    door,
                    reason="lock_until_curfew_disable_curfew",
                    enabled=False,
                    lock_time=door.settings.curfew_start,
                    unlock_time=door.settings.curfew_end,
                )
                await self._lock_in(door, reason="lock_until_curfew_hold")
            return

        await self._apply_native_curfew(door, reason="native_curfew_apply")

    async def _handle_external_changes(
        self, door: DoorRuntime, snapshot: FlapSnapshot
    ) -> None:
        """Detect app-side lock during override."""
        if not door.settings.curfew_enabled:
            return
        now = self._now(door.info.timezone)
        if door.override_until and now < door.override_until:
            if snapshot.effective_locked and snapshot.mode != LOCK_MODE_CURFEW:
                _LOGGER.info(
                    "External lock detected during override for %s; restoring curfew",
                    door.info.name,
                )
                door.override_until = None
                door.lock_until_curfew = False

    async def _apply_native_curfew(self, door: DoorRuntime, *, reason: str) -> None:
        await self._set_curfew(
            door,
            reason=reason,
            enabled=True,
            lock_time=door.settings.curfew_start,
            unlock_time=door.settings.curfew_end,
        )

    def _schedule_pending_loop(self, device_id: int) -> None:
        door = self._doors[device_id]
        if self._is_synced(door):
            self._cancel_pending_loop(door)
            return
        if door._pending_task and not door._pending_task.done():
            return

        async def _run() -> None:
            while not self._is_synced(door):
                await self._sleep(self._pending_poll_interval)
                try:
                    await self._sync_once(device_id)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception(
                        "Pending reconcile failed for %s", door.info.name
                    )
                self._notify_change()
            self._cancel_pending_loop(door)

        door._pending_task = asyncio.create_task(_run())

    def _schedule_next_transition(self, door: DoorRuntime) -> None:
        self._cancel_transition_timer(door)
        now = self._now(door.info.timezone)
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(door.info.timezone)
        delay: float | None = None

        if door.override_until and now < door.override_until:
            delay = (door.override_until - now).total_seconds()
        elif door.lock_until_curfew:
            delay = seconds_until(now, door.settings.curfew_start, tz=tz)
        elif door.settings.curfew_enabled:
            in_window = in_curfew_window(
                now, door.settings.curfew_start, door.settings.curfew_end
            )
            target = (
                door.settings.curfew_end if in_window else door.settings.curfew_start
            )
            delay = seconds_until(now, target, tz=tz)

        if delay is None or delay <= 0:
            return

        async def _run() -> None:
            await self._sleep(delay)
            try:
                await self._sync_once(door.info.device_id)
                self._notify_change()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Timer reconcile failed for %s", door.info.name)

        door._transition_task = asyncio.create_task(_run())

    def _cancel_pending_loop(self, door: DoorRuntime) -> None:
        if door._pending_task and not door._pending_task.done():
            door._pending_task.cancel()
        door._pending_task = None

    def _cancel_transition_timer(self, door: DoorRuntime) -> None:
        if door._transition_task and not door._transition_task.done():
            door._transition_task.cancel()
        door._transition_task = None

    def _notify_change(self) -> None:
        if self._on_change:
            self._on_change()
