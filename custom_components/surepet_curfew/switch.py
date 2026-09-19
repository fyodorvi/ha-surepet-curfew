"""Switch platform for SurePet Curfew."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .demo import DemoFlap


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePet Curfew switch entities."""
    flap: DemoFlap = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SurepetCurfewSwitch(entry, flap)])


class SurepetCurfewSwitch(SwitchEntity):
    """Representation of a SurePet curfew schedule switch."""

    _attr_has_entity_name = True
    _attr_name = "Curfew"

    def __init__(self, entry: ConfigEntry, flap: DemoFlap) -> None:
        """Initialize the curfew switch."""
        self._entry = entry
        self._flap = flap
        self._attr_unique_id = f"{entry.entry_id}_curfew"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=flap.name,
            manufacturer="Sure Petcare",
            model="Demo Flap",
        )

    @property
    def is_on(self) -> bool:
        """Return true if curfew schedule is enabled."""
        return self._flap.curfew_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Enable curfew schedule."""
        self._flap.curfew_enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable curfew schedule (manual lock mode)."""
        self._flap.curfew_enabled = False
        self.async_write_ha_state()
