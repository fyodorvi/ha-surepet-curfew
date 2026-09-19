"""Lock platform for SurePet Curfew."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity
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
    """Set up SurePet Curfew lock entities."""
    flap: DemoFlap = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SurepetCurfewLock(entry, flap)])


class SurepetCurfewLock(LockEntity):
    """Representation of a SurePet flap lock."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: ConfigEntry, flap: DemoFlap) -> None:
        """Initialize the lock."""
        self._entry = entry
        self._flap = flap
        self._attr_unique_id = f"{entry.entry_id}_lock"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=flap.name,
            manufacturer="Sure Petcare",
            model="Demo Flap",
        )

    @property
    def is_locked(self) -> bool:
        """Return true if the flap is locked."""
        return self._flap.locked

    async def async_lock(self, **kwargs) -> None:
        """Lock the flap."""
        self._flap.locked = True
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs) -> None:
        """Unlock the flap."""
        self._flap.locked = False
        self.async_write_ha_state()
