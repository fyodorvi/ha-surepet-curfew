"""Constants for the SurePet Curfew integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .settings_store import (
    CONF_CURFEW_ENABLED_DEVICES,
    DEFAULT_CURFEW_ENABLED,
    get_curfew_enabled_from_options,
    merge_curfew_enabled_option,
)

DOMAIN = "surepet_curfew"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CURFEW_START = "curfew_start_time"
CONF_CURFEW_END = "curfew_end_time"
CONF_CURFEW_OVERRIDE = "curfew_override_minutes"
DEFAULT_CURFEW_START = "22:00"
DEFAULT_CURFEW_END = "06:00"
DEFAULT_CURFEW_OVERRIDE = 30

PET_DOOR_MODEL = "Pet Door Connect"


def get_entry_option(entry: ConfigEntry, key: str, default: object = None) -> object:
    """Return a config value from options, falling back to entry data."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def get_stored_curfew_enabled(
    entry: ConfigEntry, device_id: int, default: bool = DEFAULT_CURFEW_ENABLED
) -> bool:
    """Return persisted curfew on/off for a device."""
    return get_curfew_enabled_from_options(dict(entry.options), device_id, default)
