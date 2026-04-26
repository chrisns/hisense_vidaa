"""DataUpdateCoordinator for the Hisense VIDAA integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cdp import HisenseCDP, HisenseCDPError, parse_inputs
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class HisenseVidaaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls TV state every SCAN_INTERVAL via CDP."""

    def __init__(self, hass: HomeAssistant, client: HisenseCDP) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{client.host}",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.client.fetch_state()
        except HisenseCDPError as err:
            raise UpdateFailed(str(err)) from err
        # Normalise: parse the flat input table into structured rows
        state["inputs_parsed"] = parse_inputs(state.get("inputs") or [])
        return state
