"""Lock platform for SurePet Curfew."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SurepetCurfewCoordinator
from .entity import SurepetCurfewEntity
from .ui_state import entity_is_locked, observed_is_locked


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePet Curfew lock entities."""
    coordinator: SurepetCurfewCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SurepetCurfewLock(coordinator, device_id)
        for device_id in coordinator.controller.doors
    )


class SurepetCurfewLock(SurepetCurfewEntity, LockEntity):
    """Representation of a Pet Door lock."""

    _attr_name = None

    def __init__(
        self,
        coordinator: SurepetCurfewCoordinator,
        device_id: int,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_lock"
        self._apply_desired_to_ha()

    def _apply_desired_to_ha(self) -> None:
        """Sync LockEntity attrs from controller desired state (not API snapshot)."""
        locked = entity_is_locked(
            self.coordinator.controller.desired_effective_locked(self._device_id)
        )
        for cached in ("is_locked", "is_locking", "is_unlocking"):
            self.__dict__.pop(cached, None)
        self._attr_is_locked = locked
        self._attr_is_locking = False
        self._attr_is_unlocking = False

    @property
    def extra_state_attributes(self) -> dict[str, str | bool | None]:
        runtime = self.coordinator.controller.doors[self._device_id]
        return {
            "sync_failed": self.coordinator.controller.sync_failed(self._device_id),
            "observed_locked": observed_is_locked(self.snapshot),
            "pending_since": (
                runtime.pending_since.isoformat() if runtime.pending_since else None
            ),
        }

    def _handle_coordinator_update(self) -> None:
        self._apply_desired_to_ha()
        super()._handle_coordinator_update()

    async def async_lock(self, **kwargs) -> None:
        self.coordinator.controller.request_lock(self._device_id)
        self._apply_desired_to_ha()
        self.async_write_ha_state()
        self.hass.async_create_task(
            self.coordinator.controller.reconcile(self._device_id),
            f"surepet_curfew_reconcile_{self._device_id}",
        )

    async def async_unlock(self, **kwargs) -> None:
        self.coordinator.controller.request_unlock(self._device_id)
        self._apply_desired_to_ha()
        self.async_write_ha_state()
        self.hass.async_create_task(
            self.coordinator.controller.reconcile(self._device_id),
            f"surepet_curfew_reconcile_{self._device_id}",
        )
