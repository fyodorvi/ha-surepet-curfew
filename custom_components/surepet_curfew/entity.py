"""Base entity for SurePet Curfew."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SurepetCurfewCoordinator
from .state import FlapSnapshot


class SurepetCurfewEntity(CoordinatorEntity[SurepetCurfewCoordinator]):
    """Base class for Pet Door entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SurepetCurfewCoordinator,
        device_id: int,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        runtime = coordinator.controller.doors[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_id))},
            name=runtime.info.name,
            manufacturer="Sure Petcare",
            model="Pet Door Connect",
        )

    @property
    def snapshot(self) -> FlapSnapshot | None:
        return self.coordinator.data.get(self._device_id)

    @property
    def available(self) -> bool:
        return self.coordinator.controller.is_available(self._device_id)
