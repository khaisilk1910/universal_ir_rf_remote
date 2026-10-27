"""Optional optimistic fan backed by any remote with named speed commands."""

from __future__ import annotations

import math

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from . import ManagerConfigEntry, RemoteRuntime, async_send
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ManagerConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.runtime_data.enable_fan:
        async_add_entities([GenericRemoteFan(entry.runtime_data)])


class GenericRemoteFan(FanEntity):
    """Optimistic fan: state only tracks commands sent through this entity."""

    _attr_has_entity_name = True
    _attr_assumed_state = True
    _attr_should_poll = False
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    )

    def __init__(self, runtime: RemoteRuntime) -> None:
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_fan"
        self._attr_name = runtime.fan_device.replace("_", " ").title()
        self._attr_speed_count = runtime.fan_speed_count
        self._attr_percentage = None
        identifier = runtime.entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=f"Universal IR RF Remote Manager - {runtime.remote_entity}",
            manufacturer="Universal IR RF Remote Manager",
            model="Optimistic fan commands",
        )

    @property
    def available(self) -> bool:
        remote = self.hass.states.get(self.runtime.remote_entity)
        return remote is not None and remote.state not in ("unknown", "unavailable")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_state_change_event(
            self.hass, [self.runtime.remote_entity], self._remote_changed,
        ))

    @callback
    def _remote_changed(self, _event) -> None:
        self.async_write_ha_state()

    @property
    def percentage(self) -> int | None:
        return self._attr_percentage

    @property
    def is_on(self) -> bool | None:
        return None if self._attr_percentage is None else self._attr_percentage > 0

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage <= 0:
            await self.async_turn_off()
            return
        level = max(1, min(self.speed_count, math.ceil(percentage * self.speed_count / 100)))
        await async_send(self.hass, self.runtime, device=self.runtime.fan_device,
                         command=f"speed_{level}")
        self._attr_percentage = round(level * 100 / self.speed_count)
        self.async_write_ha_state()

    async def async_turn_on(self, percentage: int | None = None,
                            preset_mode: str | None = None, **kwargs) -> None:
        if preset_mode is not None:
            raise ValueError("This fan has no preset modes")
        await self.async_set_percentage(
            percentage if percentage is not None else (self._attr_percentage or 100)
        )

    async def async_turn_off(self, **kwargs) -> None:
        await async_send(self.hass, self.runtime, device=self.runtime.fan_device,
                         command="turn_off")
        self._attr_percentage = 0
        self.async_write_ha_state()

