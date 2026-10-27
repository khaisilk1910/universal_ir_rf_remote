"""Per-remote, push-style metadata count sensors."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ManagerConfigEntry, RemoteRuntime
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ManagerConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([RemoteLibraryCount(entry.runtime_data)])


class RemoteLibraryCount(SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "learned_commands"
    _attr_icon = "mdi:remote"
    _attr_should_poll = False

    def __init__(self, runtime: RemoteRuntime) -> None:
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_learned_codes"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.entry_id)},
            name=f"Universal IR RF Remote Manager - {runtime.remote_entity}",
            manufacturer="Universal IR RF Remote Manager",
            model="IR/RF command metadata library",
        )

    @property
    def native_value(self) -> int | None:
        return self.runtime.library.command_count

    @property
    def extra_state_attributes(self) -> dict:
        library = self.runtime.library
        if not library.loaded:
            return {"remote_entity": self.runtime.remote_entity}
        return {
            "remote_entity": self.runtime.remote_entity,
            "total_devices": len(library.codes),
            "devices": sorted(library.codes)[:30],
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(
            self.hass, self.runtime.library.signal, self.async_write_ha_state,
        ))

