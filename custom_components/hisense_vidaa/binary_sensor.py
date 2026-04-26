"""Binary sensors — read-only diagnostics (3D signal present, HDR signal active)."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import HisenseVidaaCoordinator
from .entity import HisenseVidaaEntity


@dataclass(frozen=True, kw_only=True)
class HisenseBinaryDescription(BinarySensorEntityDescription):
    state_key: str


BINARIES: tuple[HisenseBinaryDescription, ...] = (
    HisenseBinaryDescription(
        key="three_d_signal", name="3D signal present", icon="mdi:video-3d",
        state_key="three_d_exists",
    ),
    HisenseBinaryDescription(
        key="three_d_supported", name="3D hardware supported", icon="mdi:check-circle",
        state_key="three_d_supported",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HisenseBinaryDescription(
        key="three_d_2dto3d_available", name="2D→3D conversion available",
        icon="mdi:swap-horizontal",
        state_key="three_d_2dto3d_exists",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HisenseBinaryDescription(
        key="hdr_supported", name="HDR hardware supported", icon="mdi:hdr",
        state_key="hdr_supported",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: HisenseVidaaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HisenseVidaaBinary(coordinator, entry, desc) for desc in BINARIES
    )


class HisenseVidaaBinary(HisenseVidaaEntity, BinarySensorEntity):
    entity_description: HisenseBinaryDescription

    def __init__(self, coordinator: HisenseVidaaCoordinator, entry: ConfigEntry, desc: HisenseBinaryDescription) -> None:
        super().__init__(coordinator, entry, desc.key)
        self.entity_description = desc

    @property
    def is_on(self) -> bool | None:
        v = self._data(self.entity_description.state_key)
        return None if v is None else bool(v)
