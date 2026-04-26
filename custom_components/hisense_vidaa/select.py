"""Select entities for Hisense VIDAA — picture mode, sound mode, aspect, 3D, HDR, etc."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cdp import HisenseCDP
from .const import DOMAIN
from .coordinator import HisenseVidaaCoordinator
from .entity import HisenseVidaaEntity

_LOGGER = logging.getLogger(__name__)


# Hisense enums are by-and-large undocumented but stable. These maps cover the
# common values; unknown ints are surfaced as "Mode N" so the UI is never blank.
PICTURE_MODES = {0: "Vivid", 1: "Standard", 2: "Energy Saving",
                 3: "Theater Day", 4: "Theater Night", 5: "Sport",
                 6: "Game", 7: "Calibrated"}
SOUND_MODES = {0: "Standard", 1: "Movie", 2: "Music", 3: "Speech", 4: "Late Night"}
ZOOM_MODES = {0: "16:9", 1: "Auto", 2: "4:3", 3: "Zoom 1", 4: "Zoom 2",
              5: "Just Scan", 6: "Cinema", 7: "Smart Zoom"}
THREE_D_MODES = {0: "Off", 1: "Side-by-Side", 2: "Top-Bottom",
                 3: "Frame Packing", 4: "2D→3D", 5: "Line Interlaced",
                 6: "Checkerboard", 7: "L/R Switch", 8: "Auto"}
HDR_MODES = {0: "Off", 1: "Auto", 2: "HDR10", 3: "HLG", 4: "HDR10+", 5: "Dolby Vision"}
COLOUR_TEMP = {0: "Standard", 1: "Cool", 2: "Warm 1", 3: "Warm 2"}
COLOR_GAMUT = {0: "Standard", 1: "Native", 2: "Auto"}
LOCAL_DIMMING = {0: "Off", 1: "Low", 2: "High"}
SMOOTH_MOTION = {0: "Off", 1: "Smooth", 2: "Standard", 3: "Clear"}
NOISE_REDUCTION = {0: "Off", 1: "Low", 2: "Mid", 3: "High", 4: "Auto"}
DYNAMIC_BACKLIGHT = {0: "Off", 1: "Low", 2: "Mid", 3: "High"}


@dataclass(frozen=True, kw_only=True)
class HisenseSelectDescription(SelectEntityDescription):
    state_key: str
    enum: dict[int, str]
    setter: Callable[[HisenseCDP, int], Awaitable[None]]
    available_key: str | None = None  # data key whose truthy value gates availability


SELECTS: tuple[HisenseSelectDescription, ...] = (
    HisenseSelectDescription(
        key="picture_mode", name="Picture mode", icon="mdi:palette",
        state_key="picture_mode", enum=PICTURE_MODES,
        setter=lambda c, i: c.set_picture_mode(i),
    ),
    HisenseSelectDescription(
        key="sound_mode", name="Sound mode", icon="mdi:music-note",
        state_key="sound_mode", enum=SOUND_MODES,
        setter=lambda c, i: c.set_sound_mode(i),
    ),
    HisenseSelectDescription(
        key="aspect_ratio", name="Aspect ratio", icon="mdi:aspect-ratio",
        state_key="zoom", enum=ZOOM_MODES,
        setter=lambda c, i: c.set_zoom(i),
    ),
    HisenseSelectDescription(
        # Always available when the panel supports 3D — even if no 3D signal
        # is currently detected, we still want the user to pick a forced mode
        # for the moment one arrives.
        key="three_d_mode", name="3D mode (force)", icon="mdi:video-3d",
        state_key="three_d_mode", enum=THREE_D_MODES,
        setter=lambda c, i: c.set_3d_mode(i),
        available_key="three_d_supported",
    ),
    HisenseSelectDescription(
        key="hdr_mode", name="HDR mode", icon="mdi:hdr",
        state_key="hdr_mode", enum=HDR_MODES,
        setter=lambda c, i: c.set_hdr_mode(i),
        available_key="hdr_supported",
    ),
    HisenseSelectDescription(
        key="colour_temperature", name="Colour temperature", icon="mdi:thermometer",
        state_key="color_temperature", enum=COLOUR_TEMP,
        setter=lambda c, i: c.set_color_temperature(i),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseSelectDescription(
        key="color_gamut", name="Colour gamut", icon="mdi:palette-outline",
        state_key="color_gamut", enum=COLOR_GAMUT,
        setter=lambda c, i: c.set_color_gamut(i),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseSelectDescription(
        key="local_dimming", name="Local dimming", icon="mdi:brightness-6",
        state_key="local_dimming", enum=LOCAL_DIMMING,
        setter=lambda c, i: c.set_local_dimming(i),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseSelectDescription(
        key="smooth_motion", name="Smooth motion", icon="mdi:motion-play",
        state_key="smooth_motion", enum=SMOOTH_MOTION,
        setter=lambda c, i: c.set_smooth_motion(i),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseSelectDescription(
        key="noise_reduction", name="Noise reduction", icon="mdi:waveform",
        state_key="noise_reduction", enum=NOISE_REDUCTION,
        setter=lambda c, i: c.set_noise_reduction(i),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseSelectDescription(
        key="dynamic_backlight", name="Dynamic backlight", icon="mdi:brightness-auto",
        state_key="dynamic_backlight", enum=DYNAMIC_BACKLIGHT,
        setter=lambda c, i: c.set_dynamic_backlight(i),
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HisenseVidaaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HisenseVidaaSelect(coordinator, entry, desc) for desc in SELECTS
    )


class HisenseVidaaSelect(HisenseVidaaEntity, SelectEntity):
    entity_description: HisenseSelectDescription

    def __init__(self, coordinator: HisenseVidaaCoordinator, entry: ConfigEntry, desc: HisenseSelectDescription) -> None:
        super().__init__(coordinator, entry, desc.key)
        self.entity_description = desc
        self._attr_options = list(desc.enum.values())

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        gate = self.entity_description.available_key
        if gate and not self._data(gate):
            return False
        return self._data(self.entity_description.state_key) is not None

    @property
    def current_option(self) -> str | None:
        v = self._data(self.entity_description.state_key)
        if v is None:
            return None
        try:
            return self.entity_description.enum.get(int(v), f"Mode {int(v)}")
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        # Reverse-lookup option label → int
        for k, v in self.entity_description.enum.items():
            if v == option:
                await self.entity_description.setter(self.coordinator.client, k)
                await self.coordinator.async_request_refresh()
                return
        # Allow "Mode N" pass-through for unknown enums
        if option.lower().startswith("mode "):
            try:
                num = int(option.split()[1])
            except (IndexError, ValueError):
                _LOGGER.warning("Cannot parse %s as Mode N", option)
                return
            await self.entity_description.setter(self.coordinator.client, num)
            await self.coordinator.async_request_refresh()
            return
        _LOGGER.warning("Unknown option %s for %s", option, self.entity_description.key)
