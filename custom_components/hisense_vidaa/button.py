"""Button entities — one-shot actions (CEC rediscover, picture reset)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .cdp import HisenseCDP
from .const import DOMAIN
from .coordinator import HisenseVidaaCoordinator
from .entity import HisenseVidaaEntity


@dataclass(frozen=True, kw_only=True)
class HisenseButtonDescription(ButtonEntityDescription):
    action: Callable[[HisenseCDP], Awaitable[None]]


BUTTONS: tuple[HisenseButtonDescription, ...] = (
    HisenseButtonDescription(
        key="cec_rediscover", name="Re-scan CEC bus", icon="mdi:refresh",
        action=lambda c: c.cec_rediscover(),
        entity_category=EntityCategory.CONFIG,
    ),
    HisenseButtonDescription(
        key="reset_picture", name="Reset picture defaults", icon="mdi:restore",
        action=lambda c: c.reset_picture_defaults(),
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
        HisenseVidaaButton(coordinator, entry, desc) for desc in BUTTONS
    )


class HisenseVidaaButton(HisenseVidaaEntity, ButtonEntity):
    entity_description: HisenseButtonDescription

    def __init__(self, coordinator: HisenseVidaaCoordinator, entry: ConfigEntry, desc: HisenseButtonDescription) -> None:
        super().__init__(coordinator, entry, desc.key)
        self.entity_description = desc

    async def async_press(self) -> None:
        await self.entity_description.action(self.coordinator.client)
        await self.coordinator.async_request_refresh()
