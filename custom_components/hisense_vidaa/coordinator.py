"""DataUpdateCoordinator for the Hisense VIDAA integration.

Adaptive polling: when the last fetch succeeded we poll on the user-configured
interval (default 5 s). When fetches start failing — usually because the TV
is off and port 9223 stops listening — we back off to a longer interval to
avoid log spam, and snap back to the fast cadence the moment the TV's reachable.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cdp import HisenseCDP, HisenseCDPError, parse_inputs
from .const import (
    CONF_OFFLINE_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_OFFLINE_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class HisenseVidaaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: HisenseCDP,
        entry: ConfigEntry,
    ) -> None:
        self._entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{client.host}",
            update_interval=timedelta(seconds=self._fast_seconds()),
        )
        self.client = client

    # ------- interval helpers ------------------------------------------------

    def _fast_seconds(self) -> int:
        return int(self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    def _slow_seconds(self) -> int:
        return int(self._entry.options.get(CONF_OFFLINE_INTERVAL, DEFAULT_OFFLINE_INTERVAL))

    def reload_intervals(self) -> None:
        """Called when options change — re-pin the current interval choice
        based on whether we last succeeded or failed."""
        target = self._fast_seconds() if self.last_update_success else self._slow_seconds()
        self.update_interval = timedelta(seconds=target)

    # ------- data fetch ------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.client.fetch_state()
        except HisenseCDPError as err:
            # Back off to the slow cadence while unreachable
            slow = self._slow_seconds()
            if self.update_interval != timedelta(seconds=slow):
                self.update_interval = timedelta(seconds=slow)
            raise UpdateFailed(str(err)) from err

        # Came back / still healthy — make sure we're on the fast cadence
        fast = self._fast_seconds()
        if self.update_interval != timedelta(seconds=fast):
            self.update_interval = timedelta(seconds=fast)

        state["inputs_parsed"] = parse_inputs(state.get("inputs") or [])
        return state
