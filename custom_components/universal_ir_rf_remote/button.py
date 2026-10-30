"""Per-command push-style buttons grouped under named virtual appliances."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entities

from . import ManagerConfigEntry, RemoteRuntime, async_send
from .const import DOMAIN


def appliance_device_info(runtime: RemoteRuntime, key: str, name: str, kind: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{runtime.entry.entry_id}_{key}")},
        name=name,
        manufacturer="Universal IR RF Remote Manager",
        model=f"Virtual {kind.replace('_', ' ')} appliance",
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ManagerConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    known: dict[str, SavedCommandButton] = {}

    @callback
    def synchronize() -> None:
        if not runtime.library.loaded:
            return
        expected: set[str] = set()
        added = []
        for device_id, dev in runtime.library.devices.items():
            for label, record in dev["commands"].items():
                key = f"{device_id}_{record['id']}"
                expected.add(key)
                if key not in known:
                    entity = SavedCommandButton(runtime, device_id, record["id"])
                    known[key] = entity
                    added.append(entity)
                else:
                    known[key]._refresh_metadata()
                    if known[key].entity_id is not None:
                        known[key].async_write_ha_state()
        for key in set(known) - expected:
            entity = known.pop(key)
            if entity.entity_id:
                async_get_entities(hass).async_remove(entity.entity_id)
            else:
                hass.async_create_task(entity.async_remove())
        if added:
            async_add_entities(added)

    entry.async_on_unload(async_dispatcher_connect(hass, runtime.library.signal, synchronize))
    synchronize()


class SavedCommandButton(ButtonEntity):
    """Pressing sends one stored command through the owning remote entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:remote"

    def __init__(self, runtime: RemoteRuntime, device_id: str, command_id: str) -> None:
        self.runtime = runtime
        self.device_id = device_id
        self.command_id = command_id
        self._attr_unique_id = f"{runtime.entry.entry_id}_{device_id}_{command_id}"
        self._refresh_metadata()

    def _refresh_metadata(self) -> tuple[str, str] | None:
        dev = self.runtime.library.devices.get(self.device_id)
        if dev is None:
            return None
        for label, command in dev["commands"].items():
            if command["id"] == self.command_id:
                self._attr_name = label
                self._attr_device_info = appliance_device_info(
                    self.runtime, self.device_id, dev["name"], dev.get("kind", "generic")
                )
                return dev["name"], label
        return None

    @property
    def available(self) -> bool:
        state = self.hass.states.get(self.runtime.remote_entity)
        return self._refresh_metadata() is not None and state is not None and state.state not in (
            "unavailable", "unknown"
        )

    async def async_press(self) -> None:
        found = self._refresh_metadata()
        if found is None:
            raise ValueError("Command no longer exists")
        await async_send(self.hass, self.runtime, device=found[0], command=found[1])
