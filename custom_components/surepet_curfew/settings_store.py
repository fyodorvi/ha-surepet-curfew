"""HA-free helpers for persisted integration settings."""

from __future__ import annotations

CONF_CURFEW_ENABLED_DEVICES = "curfew_enabled_devices"
DEFAULT_CURFEW_ENABLED = True


def get_curfew_enabled_from_options(
    options: dict[str, object],
    device_id: int,
    default: bool = DEFAULT_CURFEW_ENABLED,
) -> bool:
    """Return persisted curfew on/off for a device."""
    devices = options.get(CONF_CURFEW_ENABLED_DEVICES, {})
    if isinstance(devices, dict):
        return bool(devices.get(str(device_id), default))
    return default


def merge_curfew_enabled_option(
    options: dict[str, object], device_id: int, enabled: bool
) -> dict[str, object]:
    """Return options with updated per-device curfew enabled flag."""
    devices = dict(options.get(CONF_CURFEW_ENABLED_DEVICES, {}))
    devices[str(device_id)] = enabled
    return {**options, CONF_CURFEW_ENABLED_DEVICES: devices}
