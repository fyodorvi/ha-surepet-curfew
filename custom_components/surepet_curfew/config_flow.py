"""Config flow for SurePet Curfew."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_CURFEW_END,
    CONF_CURFEW_OVERRIDE,
    CONF_CURFEW_START,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_CURFEW_END,
    DEFAULT_CURFEW_OVERRIDE,
    DEFAULT_CURFEW_START,
    DOMAIN,
)

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_time(value: str) -> str:
    """Validate HH:MM time format."""
    if not TIME_PATTERN.match(value):
        raise vol.Invalid("Time must be in HH:MM format")
    return value


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_CURFEW_START, default=DEFAULT_CURFEW_START): vol.All(
            str, _validate_time
        ),
        vol.Required(CONF_CURFEW_END, default=DEFAULT_CURFEW_END): vol.All(
            str, _validate_time
        ),
        vol.Required(CONF_CURFEW_OVERRIDE, default=DEFAULT_CURFEW_OVERRIDE): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=240)
        ),
    }
)


class SurepetCurfewConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SurePet Curfew."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_USERNAME],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


async def async_get_options_flow(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
) -> config_entries.OptionsFlow:
    """Get the options flow for this handler."""
    return SurepetCurfewOptionsFlow(config_entry)


class SurepetCurfewOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for SurePet Curfew."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CURFEW_START,
                        default=self.config_entry.data.get(
                            CONF_CURFEW_START, DEFAULT_CURFEW_START
                        ),
                    ): vol.All(str, _validate_time),
                    vol.Required(
                        CONF_CURFEW_END,
                        default=self.config_entry.data.get(
                            CONF_CURFEW_END, DEFAULT_CURFEW_END
                        ),
                    ): vol.All(str, _validate_time),
                    vol.Required(
                        CONF_CURFEW_OVERRIDE,
                        default=self.config_entry.data.get(
                            CONF_CURFEW_OVERRIDE, DEFAULT_CURFEW_OVERRIDE
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=240)),
                }
            ),
        )
