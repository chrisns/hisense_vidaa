"""Hisense VIDAA TV (CDP) integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import aiohttp_client, config_validation as cv
from homeassistant.helpers.service import async_extract_config_entry_ids

from .cdp import HisenseCDP, HisenseCDPError
from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN
from .coordinator import HisenseVidaaCoordinator

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
]

_LOGGER = logging.getLogger(__name__)

SERVICE_SHOW_MESSAGE = "show_message"
SHOW_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("seconds", default=3): vol.All(vol.Coerce(float), vol.Range(min=1, max=15)),
        vol.Optional("device_id"): vol.Any(cv.string, [cv.string]),
        vol.Optional("entity_id"): vol.Any(cv.string, [cv.string]),
        vol.Optional("area_id"): vol.Any(cv.string, [cv.string]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = aiohttp_client.async_get_clientsession(hass)
    client = HisenseCDP(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        session=session,
    )
    coordinator = HisenseVidaaCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # React to options changes (scan_interval, etc.) without a full reload
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    if not hass.services.has_service(DOMAIN, SERVICE_SHOW_MESSAGE):
        async def _show_message(call: ServiceCall) -> None:
            message: str = call.data["message"]
            seconds: float = call.data.get("seconds", 3)
            target_entry_ids = await async_extract_config_entry_ids(hass, call)
            entries = (
                [hass.data[DOMAIN][eid] for eid in target_entry_ids if eid in hass.data.get(DOMAIN, {})]
                or list(hass.data.get(DOMAIN, {}).values())
            )
            for c in entries:
                try:
                    await c.client.show_message(message, seconds)
                except HisenseCDPError as err:
                    _LOGGER.error("show_message failed for %s: %s", c.client.host, err)

        hass.services.async_register(
            DOMAIN, SERVICE_SHOW_MESSAGE, _show_message, schema=SHOW_MESSAGE_SCHEMA
        )

    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: HisenseVidaaCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        coordinator.reload_intervals()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data.get(DOMAIN):
        # Last entry unloaded — remove the service so it doesn't dangle
        hass.services.async_remove(DOMAIN, SERVICE_SHOW_MESSAGE)
    return unload_ok
