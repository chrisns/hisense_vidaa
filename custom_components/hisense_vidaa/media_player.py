"""Media player entity for Hisense VIDAA TV via CDP."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .cdp import HisenseCDPError, resolve_uid
from .const import DOMAIN
from .coordinator import HisenseVidaaCoordinator

_LOGGER = logging.getLogger(__name__)

def _label(entry: dict[str, Any]) -> str:
    """Friendly label for an input. Treats the TV's placeholder
    custom_name 'wrong' (Hisense default before the user renames it)
    as no name."""
    cn = (entry.get("custom_name") or "").strip()
    if cn and cn.lower() != "wrong":
        return cn
    name = entry.get("name") or "?"
    # Strip the _UHD suffix the TV adds on capable ports for tidier UX.
    return name.replace("_UHD", "").replace("_uhd", "").strip()


SUPPORTED_FEATURES = (
    MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HisenseVidaaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HisenseVidaaMediaPlayer(coordinator, entry)])


class HisenseVidaaMediaPlayer(CoordinatorEntity[HisenseVidaaCoordinator], MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_name = None  # use device name
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_supported_features = SUPPORTED_FEATURES

    def __init__(self, coordinator: HisenseVidaaCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_media_player"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Hisense",
            model="VIDAA TV (CDP)",
            configuration_url=f"http://{coordinator.client.host}:{coordinator.client.port if hasattr(coordinator.client, 'port') else 9223}/",
        )

    # ----- helpers ---------------------------------------------------------

    @property
    def _inputs(self) -> list[dict[str, Any]]:
        return (self.coordinator.data or {}).get("inputs_parsed", [])

    @property
    def _current_uid(self) -> int | None:
        v = (self.coordinator.data or {}).get("source_uid")
        return int(v) if v is not None else None

    def _name_for_uid(self, uid: int | None) -> str | None:
        if uid is None:
            return None
        for entry in self._inputs:
            if entry["uid"] == uid:
                return _label(entry)
        return None

    # ----- standard properties ---------------------------------------------

    @property
    def state(self) -> MediaPlayerState | None:
        if not self.coordinator.last_update_success:
            return MediaPlayerState.OFF
        # If we can talk to CDP at all, the panel is on.
        return MediaPlayerState.ON

    @property
    def source_list(self) -> list[str]:
        # The TV's "available" flag means "has signal right now" — confusing for
        # source-switching, since the input the user is currently watching can
        # still come back as available=0. Show every input the firmware enumerates.
        return [_label(e) for e in self._inputs]

    @property
    def source(self) -> str | None:
        return self._name_for_uid(self._current_uid)

    @property
    def volume_level(self) -> float | None:
        v = (self.coordinator.data or {}).get("volume")
        return None if v is None else max(0.0, min(1.0, float(v) / 100.0))

    @property
    def is_volume_muted(self) -> bool | None:
        m = (self.coordinator.data or {}).get("mute")
        return None if m is None else bool(m)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {
            "source_uid": d.get("source_uid"),
            "picture_mode": d.get("picture_mode"),
            "sound_mode_id": d.get("sound_mode"),
            "three_d_signal": bool(d.get("three_d_exists")),
            "three_d_mode": d.get("three_d_mode"),
            "backlight": d.get("backlight"),
            "brightness": d.get("brightness"),
        }

    # ----- service handlers ------------------------------------------------

    async def async_select_source(self, source: str) -> None:
        try:
            uid = resolve_uid(source, self._inputs)
        except HisenseCDPError as err:
            _LOGGER.error("Cannot resolve source %r: %s", source, err)
            return
        await self.coordinator.client.set_source(uid)
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.client.set_volume(int(round(volume * 100)))
        await self.coordinator.async_request_refresh()

    async def async_volume_up(self) -> None:
        cur = (self.coordinator.data or {}).get("volume") or 0
        await self.coordinator.client.set_volume(min(100, int(cur) + 2))
        await self.coordinator.async_request_refresh()

    async def async_volume_down(self) -> None:
        cur = (self.coordinator.data or {}).get("volume") or 0
        await self.coordinator.client.set_volume(max(0, int(cur) - 2))
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.client.set_mute(mute)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.coordinator.client.set_power(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        await self.coordinator.client.set_power(False)
        await self.coordinator.async_request_refresh()
