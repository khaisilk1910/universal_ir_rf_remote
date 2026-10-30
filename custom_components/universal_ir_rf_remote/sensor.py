"""Per-appliance command count sensors; no synthetic hub library device."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import async_get as async_get_devices
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entities

from . import ManagerConfigEntry, RemoteRuntime
from .button import appliance_device_info
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ManagerConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    known: dict[str, ApplianceCommandCount] = {}

    @callback
    def synchronize() -> None:
        if not runtime.library.loaded:
            return
        devices_registry = async_get_devices(hass)
        expected = set(runtime.library.devices)
        for key, dev in runtime.library.devices.items():
            registered = devices_registry.async_get_device_by_identifier(
                (DOMAIN, f"{entry.entry_id}_{key}"), entry.entry_id
            )
            if registered is not None and registered.name != dev["name"]:
                devices_registry.async_update_device(registered.id, name=dev["name"])
            if key in known:
                known[key].async_write_ha_state()
            else:
                entity = ApplianceCommandCount(runtime, key)
                known[key] = entity
                async_add_entities([entity])
        for key in set(known) - expected:
            entity = known.pop(key)
            if entity.entity_id:
                async_get_entities(hass).async_remove(entity.entity_id)
            else:
                hass.async_create_task(entity.async_remove())
            # Device registry cleanup happens after the last associated entity
            # is removed by Home Assistant's entity registry lifecycle.

    entry.async_on_unload(async_dispatcher_connect(hass, runtime.library.signal, synchronize))
    synchronize()



class ApplianceCommandCount(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Commands"
    _attr_icon = "mdi:remote"
    _attr_should_poll = False

    def __init__(self, runtime: RemoteRuntime, device_id: str) -> None:
        self.runtime = runtime
        self.device_id = device_id
        self._attr_unique_id = f"{runtime.entry.entry_id}_{device_id}_command_count"
        dev = runtime.library.devices[device_id]
        self._attr_device_info = appliance_device_info(
            runtime, device_id, dev["name"], dev.get("kind", "generic")
        )

    @property
    def native_value(self) -> int:
        device = self.runtime.library.devices.get(self.device_id)
        return len(device["commands"]) if device else 0
