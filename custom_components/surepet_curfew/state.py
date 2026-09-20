"""Parse Sure Petcare device state for Pet Door Connect."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    from .schedule import in_curfew_window
except ImportError:
    from schedule import in_curfew_window

LOCK_MODE_UNLOCKED = 0
LOCK_MODE_LOCKED_IN = 1
LOCK_MODE_LOCKED_OUT = 2
LOCK_MODE_LOCKED_ALL = 3
LOCK_MODE_CURFEW = 4

PET_DOOR_PRODUCT_ID = 3


@dataclass(frozen=True)
class CurfewConfig:
    """Curfew schedule from control.curfew."""

    enabled: bool
    lock_time: str
    unlock_time: str


@dataclass(frozen=True)
class FlapSnapshot:
    """Normalized Pet Door state."""

    device_id: int
    name: str
    product_id: int
    online: bool
    mode: int
    curfew: CurfewConfig
    effective_locked: bool
    curfew_locked_known: bool

    @property
    def curfew_enabled(self) -> bool:
        return self.curfew.enabled

    @property
    def lock_time(self) -> str:
        return self.curfew.lock_time

    @property
    def unlock_time(self) -> str:
        return self.curfew.unlock_time


def parse_curfew_config(raw: Any) -> CurfewConfig:
    """Parse control.curfew from API (dict on Pet Door)."""
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        raw = {}
    return CurfewConfig(
        enabled=bool(raw.get("enabled", False)),
        lock_time=str(raw.get("lock_time", "22:00")),
        unlock_time=str(raw.get("unlock_time", "06:00")),
    )


def effective_locked(
    mode: int,
    curfew: CurfewConfig,
    *,
    now: datetime,
    curfew_locked: bool | None = None,
) -> tuple[bool, bool]:
    """Return (effective_locked, curfew_locked_known)."""
    if mode in (LOCK_MODE_LOCKED_IN, LOCK_MODE_LOCKED_OUT, LOCK_MODE_LOCKED_ALL):
        return True, True
    if mode == LOCK_MODE_UNLOCKED:
        return False, True
    if mode != LOCK_MODE_CURFEW:
        return False, False

    if curfew_locked is not None:
        return curfew_locked, True
    if not curfew.enabled:
        return False, False
    return in_curfew_window(now, curfew.lock_time, curfew.unlock_time), False


def snapshot_from_raw(
    raw: dict[str, Any],
    *,
    now: datetime,
    timezone_name: str | None = None,
) -> FlapSnapshot:
    """Build a FlapSnapshot from me/start device payload."""
    if timezone_name:
        from zoneinfo import ZoneInfo

        now = now.astimezone(ZoneInfo(timezone_name))

    status = raw.get("status") or {}
    control = raw.get("control") or {}
    locking_status = status.get("locking") or {}
    mode = int(locking_status.get("mode", control.get("locking", 0)))

    curfew_locked = None
    nested = locking_status.get("curfew")
    if isinstance(nested, dict) and "locked" in nested:
        curfew_locked = bool(nested["locked"])

    curfew = parse_curfew_config(control.get("curfew"))
    locked, known = effective_locked(
        mode, curfew, now=now, curfew_locked=curfew_locked
    )

    return FlapSnapshot(
        device_id=int(raw["id"]),
        name=str(raw.get("name", "Pet Door")),
        product_id=int(raw.get("product_id", PET_DOOR_PRODUCT_ID)),
        online=bool(status.get("online", False)),
        mode=mode,
        curfew=curfew,
        effective_locked=locked,
        curfew_locked_known=known,
    )
