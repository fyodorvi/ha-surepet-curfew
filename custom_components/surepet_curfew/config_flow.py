"""Config flow for SurePet Curfew."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

import aiohttp

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from surepy.exceptions import SurePetcareAuthenticationError, SurePetcareError

from .api import SurePetApi
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
    get_entry_option,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CURFEW_OVERRIDE): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=240)
        ),
    }
)

DEFAULT_OPTIONS = {
    CONF_CURFEW_START: DEFAULT_CURFEW_START,
    CONF_CURFEW_END: DEFAULT_CURFEW_END,
    CONF_CURFEW_OVERRIDE: DEFAULT_CURFEW_OVERRIDE,
}


async def _validate_credentials(username: str, password: str) -> str | None:
    """Return an error key if credentials or devices are invalid."""
    async with aiohttp.ClientSession() as session:
        api = SurePetApi(username, password, session=session)
        try:
            await api.connect()
            doors = await api.list_pet_doors()
            if not doors:
                return "no_pet_doors"
        except SurePetcareAuthenticationError:
            return "invalid_auth"
        except (SurePetcareError, aiohttp.ClientError):
            return "cannot_connect"
        finally:
            await api.close()
    return None


def _current_options(config_entry: config_entries.ConfigEntry) -> dict[str, Any]:
    """Return the effective curfew options for a config entry."""
    return {
        CONF_CURFEW_START: get_entry_option(
            config_entry, CONF_CURFEW_START, DEFAULT_CURFEW_START
        ),
        CONF_CURFEW_END: get_entry_option(
            config_entry, CONF_CURFEW_END, DEFAULT_CURFEW_END
        ),
        CONF_CURFEW_OVERRIDE: get_entry_option(
            config_entry, CONF_CURFEW_OVERRIDE, DEFAULT_CURFEW_OVERRIDE
        ),
    }


class SurepetCurfewConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SurePet Curfew."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SurepetCurfewOptionsFlow:
        """Get the options flow for this handler."""
        return SurepetCurfewOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            credential_error = await _validate_credentials(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if credential_error:
                errors["base"] = credential_error
                return self.async_show_form(
                    step_id="user",
                    data_schema=STEP_USER_DATA_SCHEMA,
                    errors=errors,
                )

            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_USERNAME],
                data={
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                },
                options=DEFAULT_OPTIONS,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow updating Sure Petcare credentials after setup."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            credential_error = await _validate_credentials(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if credential_error:
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_USERNAME, default=entry.data[CONF_USERNAME]
                            ): str,
                            vol.Required(CONF_PASSWORD): str,
                        }
                    ),
                    errors={"base": credential_error},
                )

            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_mismatch()

            return self.async_update_reload_and_abort(
                entry,
                data_updates={
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                },
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME, default=entry.data[CONF_USERNAME]
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
        )


class SurepetCurfewOptionsFlow(OptionsFlowWithReload):
    """Handle options flow for SurePet Curfew."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage curfew options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **_current_options(self.config_entry),
                    CONF_CURFEW_OVERRIDE: user_input[CONF_CURFEW_OVERRIDE],
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA,
                {
                    CONF_CURFEW_OVERRIDE: _current_options(self.config_entry)[
                        CONF_CURFEW_OVERRIDE
                    ],
                },
            ),
        )
