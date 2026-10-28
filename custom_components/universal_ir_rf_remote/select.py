"""Optional speed/command selector for virtual fan appliances.

There is deliberately no synthetic power-off command: users can only select
actual signals they imported or learned. Without an off packet, these fans
should not pretend to have a reliable off state.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entities

from . import ManagerConfigEntry, RemoteRuntime, async_send
from .button import appliance_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ManagerConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    known: dict[str, FanSpeedSelect] = {}

    @callback
    def synchronize() -> None:
        if not runtime.library.loaded:
            return
        expected = {key for key, dev in runtime.library.devices.items()
                    if dev.get("kind") == "fan" and dev["commands"]}
        for key in expected:
            if key not in known:
                entity = FanSpeedSelect(runtime, key)
                known[key] = entity
                async_add_entities([entity])
            elif known[key].entity_id:
                known[key].async_write_ha_state()
        for key in set(known) - expected:
            entity = known.pop(key)
            if entity.entity_id:
                async_get_entities(hass).async_remove(entity.entity_id)
            else:
                hass.async_create_task(entity.async_remove())

    entry.async_on_unload(async_dispatcher_connect(hass, runtime.library.signal, synchronize))
    synchronize()


class FanSpeedSelect(SelectEntity):
    """Choose any learned or imported fan command; no guessed speeds."""

    _attr_has_entity_name = True
    _attr_name = "Remote command"
    _attr_icon = "mdi:fan"
    _attr_should_poll = False

    def __init__(self, runtime: RemoteRuntime, device_id: str) -> None:
        self.runtime = runtime
        self.device_id = device_id
        self._attr_unique_id = f"{runtime.entry.entry_id}_{device_id}_fan_commands"
        self._attr_current_option = None
        dev = runtime.library.devices[device_id]
        self._attr_device_info = appliance_device_info(runtime, device_id, dev["name"], "fan")

    @property
    def options(self) -> list[str]:
        device = self.runtime.library.devices.get(self.device_id)
        return list(device["commands"]) if device else []

    @property
    def available(self) -> bool:
        state = self.hass.states.get(self.runtime.remote_entity)
        return bool(self.options) and state is not None and state.state not in (
            "unavailable", "unknown"
        )

    @property
    def current_option(self) -> str | None:
        return self._attr_current_option if self._attr_current_option in self.options else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError("Unknown fan command")
        dev = self.runtime.library.devices[self.device_id]
        await async_send(self.hass, self.runtime, device=dev["name"], command=option)
        self._attr_current_option = option
        self.async_write_ha_state()
