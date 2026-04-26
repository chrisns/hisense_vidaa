"""Switch entities — freeze, eco sensor, 2D→3D conversion, headphone-mute-TV."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cdp import HisenseCDP
from .const import DOMAIN
from .coordinator import HisenseVidaaCoordinator
from .entity import HisenseVidaaEntity


@dataclass(frozen=True, kw_only=True)
class HisenseSwitchDescription(SwitchEntityDescription):
    state_key: str
    setter: Callable[[HisenseCDP, bool], Awaitable[None]]
    available_key: str | None = None


SWITCHES: tuple[HisenseSwitchDescription, ...] = (
    HisenseSwitchDescription(
        key="freeze", name="Picture freeze", icon="mdi:pause-circle",
        state_key="freeze",
        setter=lambda c, v: c.set_freeze(v),
    ),
    HisenseSwitchDescription(
        key="eco_sensor", name="Eco light sensor", icon="mdi:leaf",
        state_key="eco_sensor",
        setter=lambda c, v: c.set_eco_sensor(v),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseSwitchDescription(
        key="three_d_2dto3d", name="2D→3D conversion", icon="mdi:video-3d",
        state_key="three_d_2dto3d",
        setter=lambda c, v: c.set_3d_2dto3d(v),
        available_key="three_d_supported",
    ),
    HisenseSwitchDescription(
        key="headphone_mute_tv", name="Mute TV when headphones plug in",
        icon="mdi:headphones",
        state_key="headphone_mute_tv",
        setter=lambda c, v: c.set_headphone_mute_tv(v),
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
        HisenseVidaaSwitch(coordinator, entry, desc) for desc in SWITCHES
    )


class HisenseVidaaSwitch(HisenseVidaaEntity, SwitchEntity):
    entity_description: HisenseSwitchDescription

    def __init__(self, coordinator: HisenseVidaaCoordinator, entry: ConfigEntry, desc: HisenseSwitchDescription) -> None:
        super().__init__(coordinator, entry, desc.key)
        self.entity_description = desc

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        gate = self.entity_description.available_key
        if gate and not self._data(gate):
            return False
        return self._data(self.entity_description.state_key) is not None

    @property
    def is_on(self) -> bool | None:
        v = self._data(self.entity_description.state_key)
        return None if v is None else bool(v)

    async def async_turn_on(self, **kwargs) -> None:
        await self.entity_description.setter(self.coordinator.client, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.entity_description.setter(self.coordinator.client, False)
        await self.coordinator.async_request_refresh()
