"""Config flow for Hisense VIDAA (CDP)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import aiohttp_client

from .cdp import HisenseCDP, HisenseCDPError
from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN

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
                # Probe one read; surfaces "cannot_connect" cleanly if 9223 is closed.
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
