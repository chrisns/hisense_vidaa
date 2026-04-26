"""Number entities — picture tuning sliders."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cdp import HisenseCDP
from .const import DOMAIN
from .coordinator import HisenseVidaaCoordinator
from .entity import HisenseVidaaEntity


@dataclass(frozen=True, kw_only=True)
class HisenseNumberDescription(NumberEntityDescription):
    state_key: str
    setter: Callable[[HisenseCDP, int], Awaitable[None]]


NUMBERS: tuple[HisenseNumberDescription, ...] = (
    HisenseNumberDescription(
        key="backlight", name="Backlight", icon="mdi:brightness-7",
        native_min_value=0, native_max_value=100, native_step=1,
        native_unit_of_measurement="%", mode=NumberMode.SLIDER,
        state_key="backlight",
        setter=lambda c, v: c.set_backlight(v),
    ),
    HisenseNumberDescription(
        key="brightness", name="Brightness", icon="mdi:brightness-6",
        native_min_value=0, native_max_value=100, native_step=1,
        native_unit_of_measurement="%", mode=NumberMode.SLIDER,
        state_key="brightness",
        setter=lambda c, v: c.set_brightness(v),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseNumberDescription(
        key="contrast", name="Contrast", icon="mdi:contrast-circle",
        native_min_value=0, native_max_value=100, native_step=1,
        native_unit_of_measurement="%", mode=NumberMode.SLIDER,
        state_key="contrast",
        setter=lambda c, v: c.set_contrast(v),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseNumberDescription(
        key="colour_intensity", name="Colour intensity", icon="mdi:palette",
        native_min_value=0, native_max_value=100, native_step=1,
        native_unit_of_measurement="%", mode=NumberMode.SLIDER,
        state_key="colour_intensity",
        setter=lambda c, v: c.set_colour_intensity(v),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseNumberDescription(
        key="sharpness", name="Sharpness", icon="mdi:image-edit",
        native_min_value=0, native_max_value=100, native_step=1,
        native_unit_of_measurement="%", mode=NumberMode.SLIDER,
        state_key="sharpness",
        setter=lambda c, v: c.set_sharpness(v),
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
        HisenseVidaaNumber(coordinator, entry, desc) for desc in NUMBERS
    )


class HisenseVidaaNumber(HisenseVidaaEntity, NumberEntity):
    entity_description: HisenseNumberDescription

    def __init__(self, coordinator: HisenseVidaaCoordinator, entry: ConfigEntry, desc: HisenseNumberDescription) -> None:
        super().__init__(coordinator, entry, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> float | None:
        v = self._data(self.entity_description.state_key)
        return None if v is None else float(v)

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.setter(self.coordinator.client, int(value))
        await self.coordinator.async_request_refresh()
