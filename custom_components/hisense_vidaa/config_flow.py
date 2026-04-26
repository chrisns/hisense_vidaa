"""Config flow + Options flow for Hisense VIDAA (CDP)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

from .cdp import HisenseCDP, HisenseCDPError
from .const import (
    CONF_HOST,
    CONF_OFFLINE_INTERVAL,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_OFFLINE_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class HisenseVidaaFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            session = aiohttp_client.async_get_clientsession(self.hass)
            client = HisenseCDP(host=host, port=port, session=session)
            try:
                await client.evaluate("model.source.getCurrentSource()")
            except HisenseCDPError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Hisense VIDAA ({host})",
                    data={CONF_HOST: host, CONF_PORT: port},
                )
        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return HisenseVidaaOptionsFlow(entry)


class HisenseVidaaOptionsFlow(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                vol.Optional(
                    CONF_OFFLINE_INTERVAL,
                    default=current.get(CONF_OFFLINE_INTERVAL, DEFAULT_OFFLINE_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
