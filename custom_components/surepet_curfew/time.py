"""Time platform for SurePet Curfew."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CURFEW_END, CONF_CURFEW_START, DOMAIN
from .coordinator import SurepetCurfewCoordinator
from .entity import SurepetCurfewEntity
from .schedule import format_hhmm, parse_hhmm


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePet Curfew time entities."""
    coordinator: SurepetCurfewCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SurepetCurfewTime] = []
    for device_id in coordinator.controller.doors:
        entities.append(
            SurepetCurfewTime(coordinator, device_id, CONF_CURFEW_START, "Lock time")
        )
        entities.append(
            SurepetCurfewTime(coordinator, device_id, CONF_CURFEW_END, "Unlock time")
        )
    async_add_entities(entities)


class SurepetCurfewTime(SurepetCurfewEntity, TimeEntity):
    """Representation of a Pet Door curfew start or end time."""

    def __init__(
        self,
        coordinator: SurepetCurfewCoordinator,
        device_id: int,
        setting_key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._setting_key = setting_key
        self._attr_name = name
        suffix = "curfew_start" if setting_key == CONF_CURFEW_START else "curfew_end"
        self._attr_unique_id = f"{device_id}_{suffix}"

    @property
    def native_value(self) -> time | None:
        runtime = self.coordinator.controller.doors[self._device_id]
        hhmm = (
            runtime.settings.curfew_start
            if self._setting_key == CONF_CURFEW_START
            else runtime.settings.curfew_end
        )
        return parse_hhmm(hhmm)

    async def async_set_value(self, value: time) -> None:
        """Update curfew time, persist, and reconcile with the door."""
        runtime = self.coordinator.controller.doors[self._device_id]
        hhmm = format_hhmm(value)
        if self._setting_key == CONF_CURFEW_START:
            curfew_start, curfew_end = hhmm, runtime.settings.curfew_end
        else:
            curfew_start, curfew_end = runtime.settings.curfew_start, hhmm

        await self.coordinator.async_apply_curfew_times(
            self._device_id,
            curfew_start=curfew_start,
            curfew_end=curfew_end,
        )
        self.async_write_ha_state()
