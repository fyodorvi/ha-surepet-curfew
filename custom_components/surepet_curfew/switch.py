"""Switch platform for SurePet Curfew."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SurepetCurfewCoordinator
from .entity import SurepetCurfewEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePet Curfew switch entities."""
    coordinator: SurepetCurfewCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SurepetCurfewSwitch(coordinator, device_id)
        for device_id in coordinator.controller.doors
    )


class SurepetCurfewSwitch(SurepetCurfewEntity, SwitchEntity):
    """Representation of a Pet Door curfew schedule switch."""

    _attr_name = "Curfew"

    def __init__(
        self,
        coordinator: SurepetCurfewCoordinator,
        device_id: int,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_curfew"

    @property
    def is_on(self) -> bool:
        runtime = self.coordinator.controller.doors[self._device_id]
        return runtime.settings.curfew_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_curfew_enabled(self._device_id, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_curfew_enabled(self._device_id, False)
        self.async_write_ha_state()
