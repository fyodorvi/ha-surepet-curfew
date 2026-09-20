"""Sure Petcare API wrapper with retries."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

import aiohttp
from surepy import Surepy
from surepy.const import BASE_RESOURCE, CONTROL_RESOURCE, MESTART_RESOURCE
from surepy.enums import EntityType, LockState
from surepy.exceptions import SurePetcareAuthenticationError, SurePetcareError

try:
    from .schedule import local_now
    from .state import FlapSnapshot, PET_DOOR_PRODUCT_ID, snapshot_from_raw
except ImportError:
    from schedule import local_now
    from state import FlapSnapshot, PET_DOOR_PRODUCT_ID, snapshot_from_raw

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_RETRIES = 4
DEFAULT_BACKOFF = (1.0, 2.0, 4.0)


@dataclass(frozen=True)
class PetDoorInfo:
    """Discovered Pet Door Connect."""

    device_id: int
    name: str
    household_id: int
    timezone: str


class SurePetApi:
    """Async wrapper around surepy for Pet Door Connect."""

    def __init__(
        self,
        email: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._email = email
        self._password = password
        self._session = session
        self._owns_session = session is None
        self._surepy: Surepy | None = None
        self._household_timezones: dict[int, str] = {}

    async def connect(self) -> None:
        """Authenticate and load household metadata."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        self._surepy = Surepy(
            email=self._email,
            password=self._password,
            session=self._session,
        )
        await self._retry(self._surepy.sac.get_token)
        me = await self._retry(lambda: self._surepy.sac.call("GET", MESTART_RESOURCE))
        for household in (me or {}).get("data", {}).get("households", []):
            tz = household.get("timezone", {}).get("timezone", "UTC")
            self._household_timezones[int(household["id"])] = tz

    async def close(self) -> None:
        """Close the HTTP session if we own it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
        self._session = None
        self._surepy = None

    async def list_pet_doors(self) -> list[PetDoorInfo]:
        """Return Pet Door Connect devices only."""
        assert self._surepy is not None
        entities = await self._retry(lambda: self._surepy.get_entities(refresh=True))
        doors: list[PetDoorInfo] = []
        for entity in entities.values():
            if entity.type != EntityType.PET_FLAP:
                continue
            household_id = int(entity.household_id)
            doors.append(
                PetDoorInfo(
                    device_id=int(entity.id),
                    name=str(entity.name),
                    household_id=household_id,
                    timezone=self._household_timezones.get(household_id, "UTC"),
                )
            )
        return doors

    def timezone_for(self, household_id: int) -> str:
        return self._household_timezones.get(household_id, "UTC")

    async def get_snapshot(
        self,
        device_id: int,
        *,
        household_id: int,
        now: datetime | None = None,
    ) -> FlapSnapshot:
        """Fetch current device state."""
        assert self._surepy is not None
        resource = (
            f"{BASE_RESOURCE}/device/{device_id}"
            "?with%5B%5D=control&with%5B%5D=status"
        )

        async def _fetch() -> dict[str, Any]:
            response = await self._surepy.sac.call("GET", resource)
            if not response or "data" not in response:
                raise SurePetcareError(f"Device {device_id} not found")
            return response["data"]

        raw = await self._retry(_fetch)
        tz = self.timezone_for(household_id)
        current = now or local_now(tz)
        return snapshot_from_raw(raw, now=current, timezone_name=tz)

    async def set_lock_mode(self, device_id: int, mode: LockState) -> None:
        """Set locking mode via control endpoint."""
        assert self._surepy is not None

        async def _put() -> None:
            resource = CONTROL_RESOURCE.format(
                BASE_RESOURCE=BASE_RESOURCE, device_id=device_id
            )
            response = await self._surepy.sac.call(
                "PUT",
                resource,
                json={"locking": int(mode.value)},
            )
            if not response:
                raise SurePetcareError(f"Failed to set lock mode {mode.name}")

        await self._retry(_put)

    async def set_curfew(
        self,
        device_id: int,
        *,
        enabled: bool,
        lock_time: str,
        unlock_time: str,
    ) -> None:
        """Set Pet Door curfew as a single dict (not surepy's array helper)."""
        assert self._surepy is not None
        payload = {
            "curfew": {
                "enabled": enabled,
                "lock_time": lock_time,
                "unlock_time": unlock_time,
            }
        }
        if enabled:
            payload["locking"] = LockState.CURFEW.value

        async def _put() -> None:
            resource = CONTROL_RESOURCE.format(
                BASE_RESOURCE=BASE_RESOURCE, device_id=device_id
            )
            response = await self._surepy.sac.call("PUT", resource, json=payload)
            if not response:
                raise SurePetcareError("Failed to set curfew")

        await self._retry(_put)

    async def unlock(self, device_id: int) -> None:
        await self.set_lock_mode(device_id, LockState.UNLOCKED)

    async def lock_in(self, device_id: int) -> None:
        await self.set_lock_mode(device_id, LockState.LOCKED_IN)

    async def _retry(
        self,
        func: Callable[[], Awaitable[T]],
        *,
        retries: int = DEFAULT_RETRIES,
    ) -> T:
        delays = list(DEFAULT_BACKOFF)
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                return await func()
            except SurePetcareAuthenticationError:
                raise
            except (SurePetcareError, aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_error = err
                if attempt >= retries - 1:
                    break
                delay = delays[min(attempt, len(delays) - 1)]
                _LOGGER.debug("Retry %s/%s after error: %s", attempt + 1, retries, err)
                await asyncio.sleep(delay)
        assert last_error is not None
        raise last_error
