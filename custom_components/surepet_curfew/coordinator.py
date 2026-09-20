"""Data update coordinator for SurePet Curfew."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from surepy.exceptions import SurePetcareAuthenticationError, SurePetcareError

from .api import SurePetApi
from .const import (
    CONF_CURFEW_END,
    CONF_CURFEW_OVERRIDE,
    CONF_CURFEW_START,
    DEFAULT_CURFEW_END,
    DEFAULT_CURFEW_OVERRIDE,
    DEFAULT_CURFEW_START,
    DOMAIN,
    get_entry_option,
    get_stored_curfew_enabled,
    merge_curfew_enabled_option,
)
from .controller import DoorSettings, FlapController
from .state import FlapSnapshot

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


class SurepetCurfewCoordinator(DataUpdateCoordinator[dict[int, FlapSnapshot]]):
    """Fetch and reconcile Sure Petcare Pet Door state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.api = SurePetApi(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            session=async_get_clientsession(hass),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.controller = FlapController(self.api, on_change=self._push_controller_state)

    async def async_setup(self) -> None:
        """Connect and register doors."""
        await self.api.connect()
        doors = await self.api.list_pet_doors()
        if not doors:
            raise UpdateFailed("No Pet Door Connect devices found in this account")

        for door in doors:
            self.controller.register_door(
                door,
                DoorSettings(
                    curfew_enabled=get_stored_curfew_enabled(
                        self.entry, door.device_id
                    ),
                    curfew_start=str(
                        get_entry_option(
                            self.entry, CONF_CURFEW_START, DEFAULT_CURFEW_START
                        )
                    ),
                    curfew_end=str(
                        get_entry_option(
                            self.entry, CONF_CURFEW_END, DEFAULT_CURFEW_END
                        )
                    ),
                    override_minutes=int(
                        get_entry_option(
                            self.entry,
                            CONF_CURFEW_OVERRIDE,
                            DEFAULT_CURFEW_OVERRIDE,
                        )
                    ),
                ),
            )

    async def async_shutdown(self) -> None:
        await self.controller.shutdown()
        await self.api.close()

    def _push_controller_state(self) -> None:
        snapshots = {
            device_id: door.snapshot
            for device_id, door in self.controller.doors.items()
            if door.snapshot is not None
        }
        if snapshots:
            self.async_set_updated_data(snapshots)

    async def _async_update_data(self) -> dict[int, FlapSnapshot]:
        snapshots: dict[int, FlapSnapshot] = {}
        for device_id in self.controller.doors:
            try:
                snapshots[device_id] = await self.controller.refresh(device_id)
            except SurePetcareAuthenticationError as err:
                raise ConfigEntryAuthFailed("Invalid Sure Petcare credentials") from err
            except SurePetcareError as err:
                raise UpdateFailed(str(err)) from err
        return snapshots

    def door_settings(self) -> DoorSettings:
        return DoorSettings(
            curfew_enabled=any(
                runtime.settings.curfew_enabled
                for runtime in self.controller.doors.values()
            ),
            curfew_start=str(
                get_entry_option(self.entry, CONF_CURFEW_START, DEFAULT_CURFEW_START)
            ),
            curfew_end=str(
                get_entry_option(self.entry, CONF_CURFEW_END, DEFAULT_CURFEW_END)
            ),
            override_minutes=int(
                get_entry_option(
                    self.entry, CONF_CURFEW_OVERRIDE, DEFAULT_CURFEW_OVERRIDE
                )
            ),
        )

    def apply_entry_options(self) -> None:
        settings = self.door_settings()
        for device_id, runtime in self.controller.doors.items():
            runtime.settings = DoorSettings(
                curfew_enabled=runtime.settings.curfew_enabled,
                curfew_start=settings.curfew_start,
                curfew_end=settings.curfew_end,
                override_minutes=settings.override_minutes,
            )
            self.controller.update_settings(device_id, runtime.settings)

    async def async_apply_curfew_times(
        self,
        device_id: int,
        *,
        curfew_start: str,
        curfew_end: str,
    ) -> None:
        """Persist curfew times and push them to all doors without reloading."""
        new_options = {
            **self.entry.options,
            CONF_CURFEW_START: curfew_start,
            CONF_CURFEW_END: curfew_end,
        }
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)

        for dev_id, runtime in self.controller.doors.items():
            settings = DoorSettings(
                curfew_enabled=runtime.settings.curfew_enabled,
                curfew_start=curfew_start,
                curfew_end=curfew_end,
                override_minutes=runtime.settings.override_minutes,
            )
            self.controller.update_settings(dev_id, settings)

        self.hass.async_create_task(
            self.controller.push_curfew_schedule(device_id),
            f"surepet_curfew_schedule_{device_id}",
        )

    async def async_set_curfew_enabled(self, device_id: int, enabled: bool) -> None:
        """Persist curfew on/off and reconcile with the door without reloading."""
        new_options = merge_curfew_enabled_option(
            dict(self.entry.options), device_id, enabled
        )
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        self.controller.request_curfew_enabled(device_id, enabled)

        self.hass.async_create_task(
            self.controller.reconcile(device_id),
            f"surepet_curfew_reconcile_{device_id}",
        )
