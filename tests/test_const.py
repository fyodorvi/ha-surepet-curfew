"""Tests for persisted settings helpers."""

from __future__ import annotations

from settings_store import (
    CONF_CURFEW_ENABLED_DEVICES,
    get_curfew_enabled_from_options,
    merge_curfew_enabled_option,
)


def test_get_curfew_enabled_from_options_defaults_to_on() -> None:
    assert get_curfew_enabled_from_options({}, 1) is True


def test_get_curfew_enabled_from_options_reads_device_map() -> None:
    options = {CONF_CURFEW_ENABLED_DEVICES: {"1": False, "2": True}}
    assert get_curfew_enabled_from_options(options, 1) is False
    assert get_curfew_enabled_from_options(options, 2) is True


def test_merge_curfew_enabled_option_preserves_other_options() -> None:
    options = {
        "curfew_override_minutes": 45,
        CONF_CURFEW_ENABLED_DEVICES: {"1": True},
    }
    merged = merge_curfew_enabled_option(options, 1, False)

    assert merged["curfew_override_minutes"] == 45
    assert merged[CONF_CURFEW_ENABLED_DEVICES] == {"1": False}
