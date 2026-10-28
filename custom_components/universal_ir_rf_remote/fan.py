"""Fans attached to explicitly selected virtual appliances (not the Broadlink hub).

A fan is created only after the user maps *existing* commands in Options.
The legacy single-fan entity is retained for installations that have not yet
migrated, and is disabled automatically when a mapped fan is configured.
"""

from __future__ import annotations


from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entities
from homeassistant.helpers.event import async_track_state_change_event

from . import ManagerConfigEntry, RemoteRuntime, async_send
from .button import appliance_device_info
from .const import DOMAIN


def _percentage_to_level(percentage: float, speed_count: int) -> int:
    """Snap a dashboard percentage to the nearest *real* fan speed.

    HA's Tile slider emits fractional 100 / speed_count steps, while the
    fan service may convert those values to integers before delivery.
    Prefer the closest physical step, not ceil(): e.g. the displayed 17%
    is still level 1 of a six-speed fan, never level 2.
    This pure calculation does not call services or perform any I/O.
    """
    count = max(1, speed_count)
    return max(1, min(count, int(percentage * count / 100 + 0.5)))


async def async_setup_entry(
    hass: HomeAssistant, entry: ManagerConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    known: dict[str, MappedRemoteFan] = {}

    @callback
    def synchronize() -> None:
        if not runtime.library.loaded:
            return
        wanted = {key for key, device in runtime.library.devices.items()
                  if isinstance(device.get("fan"), dict) and device["fan"].get("speeds")}
        new_entities = []
        for key in wanted:
            if key not in known:
                fan = MappedRemoteFan(runtime, key)
                known[key] = fan
                new_entities.append(fan)
            elif known[key].entity_id:
                known[key]._refresh_details()
                known[key].async_write_ha_state()
        for key in set(known) - wanted:
            removed = known.pop(key)
            if removed.entity_id:
                async_get_entities(hass).async_remove(removed.entity_id)
            else:
                hass.async_create_task(removed.async_remove())
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, runtime.library.signal, synchronize))
    synchronize()
    if runtime.enable_fan:
        async_add_entities([GenericRemoteFan(runtime)])
    else:
        # Drop the outdated registry entry once the user disables the old fan.
        old_unique_id = f"{entry.entry_id}_fan"
        registry = async_get_entities(hass)
        old = registry.async_get_entity_id("fan", DOMAIN, old_unique_id)
        if old:
            registry.async_remove(old)


class MappedRemoteFan(FanEntity):
    """Optimistic multi-speed fan using stable IDs for speed and off commands."""

    _attr_has_entity_name = True
    _attr_name = None
    # A single Home Assistant power toggle instead of separate flash ON/OFF icons.
    # RF state is optimistic: the last successfully sent command, not hardware feedback.
    _attr_assumed_state = False
    _attr_should_poll = False
    _attr_icon = "mdi:fan"

    def __init__(self, runtime: RemoteRuntime, device_id: str) -> None:
        self.runtime = runtime
        self.device_id = device_id
        self._attr_unique_id = f"{runtime.entry.entry_id}_{device_id}_mapped_fan"
        self._attr_percentage = None
        self._last_on_level: int | None = None
        self._refresh_details()

    def _config(self) -> dict:
        dev = self.runtime.library.devices.get(self.device_id, {})
        return dev.get("fan") or {}

    def _refresh_details(self) -> None:
        dev = self.runtime.library.devices.get(self.device_id)
        if not dev:
            return
        self._attr_device_info = appliance_device_info(
            self.runtime, self.device_id, dev["name"], dev.get("kind", "fan")
        )
        config = self._config()
        self._attr_speed_count = max(1, len(config.get("speeds", [])))
        self._attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON
        if self._off_command_id():
            self._attr_supported_features |= FanEntityFeature.TURN_OFF

    @property
    def speed_count(self) -> int:
        """Stay in sync when the user edits the saved speed mapping."""
        return max(1, len(self._config().get("speeds", [])))

    @property
    def supported_features(self) -> FanEntityFeature:
        features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON
        if self._off_command_id():
            features |= FanEntityFeature.TURN_OFF
        return features

    def _off_command_id(self) -> str | None:
        """Resolve an explicit OFF mapping, or a safely named existing OFF code.

        The fallback supports upgrades where an appliance already has a
        ``turn_off`` button but the Fan mapping was created without it.
        Do not infer OFF from a power toggle or any of the speed commands.
        """
        configured = self._config().get("off")
        if configured:
            return configured
        device = self.runtime.library.devices.get(self.device_id, {})
        speed_ids = set(self._config().get("speeds", []))
        for label, record in device.get("commands", {}).items():
            if (label.strip().casefold() in ("turn_off", "off", "power_off")
                    and isinstance(record, dict)
                    and record.get("id") not in speed_ids):
                return record.get("id")
        return None

    def _command(self, command_id: str) -> tuple[str, str]:
        dev = self.runtime.library.devices.get(self.device_id)
        if not dev:
            raise ServiceValidationError("The selected fan appliance was removed")
        for label, record in dev["commands"].items():
            if record.get("id") == command_id:
                return dev["name"], label
        raise ServiceValidationError("The fan command no longer exists; edit its speed mapping")

    @property
    def available(self) -> bool:
        remote = self.hass.states.get(self.runtime.remote_entity)
        return (bool(self._config().get("speeds"))
                and remote is not None and remote.state not in ("unknown", "unavailable"))

    @property
    def percentage(self) -> int | None:
        return self._attr_percentage

    @property
    def is_on(self) -> bool | None:
        return None if self._attr_percentage is None else self._attr_percentage > 0

    async def _async_send_speed_level(self, level: int) -> None:
        """Send a discrete speed exactly once and remember the last ON level."""
        self._refresh_details()
        speeds = self._config().get("speeds", [])
        if not speeds:
            raise ServiceValidationError("No speed commands mapped for this fan")
        level = max(1, min(len(speeds), level))
        device, command = self._command(speeds[level - 1])
        await async_send(self.hass, self.runtime, device=device, command=command)
        self._last_on_level = level
        self._attr_percentage = round(level * 100 / len(speeds))
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage <= 0:
            await self.async_turn_off()
            return
        speeds = self._config().get("speeds", [])
        if not speeds:
            raise ServiceValidationError("No speed commands mapped for this fan")
        level = _percentage_to_level(percentage, len(speeds))
        await self._async_send_speed_level(level)

    async def async_turn_on(self, percentage: int | None = None,
                            preset_mode: str | None = None, **kwargs) -> None:
        if preset_mode is not None:
            raise ServiceValidationError("Fan has no preset modes")
        if percentage is not None:
            await self.async_set_percentage(percentage)
            return
        # Do not round-trip through a percentage: a 6-speed fan's first level
        # is displayed as 17%, which would otherwise round UP to level two.
        await self._async_send_speed_level(self._last_on_level or 1)

    async def async_turn_off(self, **kwargs) -> None:
        off = self._off_command_id()
        if not off:
            raise ServiceValidationError(
                "No OFF signal available. Save a turn_off code or map an OFF signal in Options."
            )
        device, command = self._command(off)
        await async_send(self.hass, self.runtime, device=device, command=command)
        self._attr_percentage = 0
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_state_change_event(
            self.hass, [self.runtime.remote_entity], self._remote_changed,
        ))
        self.async_on_remove(async_dispatcher_connect(
            self.hass, self.runtime.command_signal, self._command_sent,
        ))

    @callback
    def _command_sent(self, device_id: str, command_id: str) -> None:
        """Reflect a Press/select/service command in this particular fan.

        Command IDs, not editable labels, are the authoritative mapping.
        Only a successful send through this integration triggers this signal.
        """
        if device_id != self.device_id:
            return
        speeds = self._config().get("speeds", [])
        if command_id in speeds:
            level = speeds.index(command_id) + 1
            self._last_on_level = level
            self._attr_percentage = round(level * 100 / len(speeds))
        elif command_id == self._off_command_id():
            self._attr_percentage = 0
            # Keep _last_on_level for next power-on, as physical remotes do.
        else:
            # E.g. light, reverse, and a power *toggle* do not prove ON/OFF.
            return
        self.async_write_ha_state()

    @callback
    def _remote_changed(self, _event) -> None:
        self.async_write_ha_state()


class GenericRemoteFan(FanEntity):
    """Legacy single fan: used only until the old settings are migrated."""

    _attr_has_entity_name = True
    # A single Home Assistant power toggle instead of separate flash ON/OFF icons.
    # RF state is optimistic: the last successfully sent command, not hardware feedback.
    _attr_assumed_state = False
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
        self._last_on_level: int | None = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.entry_id)},
            name=f"Universal IR RF Remote Manager - {runtime.remote_entity}",
            manufacturer="Universal IR RF Remote Manager",
            model="Legacy fan (migrate in Configure > Remote and fan settings)",
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
        self.async_on_remove(async_dispatcher_connect(
            self.hass, self.runtime.command_signal, self._command_sent,
        ))

    @callback
    def _command_sent(self, device_id: str, command_id: str) -> None:
        """Keep the optional legacy fan in sync with its own saved buttons."""
        library = self.runtime.library
        if not library or not library.loaded:
            return
        found = library._find(self.runtime.fan_device)
        if not found or found[0] != device_id:
            return
        label = next((label for label, record in found[1]["commands"].items()
                      if record.get("id") == command_id), None)
        if label is None:
            return
        if label == "turn_off":
            self._attr_percentage = 0
        elif label.startswith("speed_") and label[6:].isdigit():
            level = int(label[6:])
            if not 1 <= level <= self.speed_count:
                return
            self._last_on_level = level
            self._attr_percentage = round(level * 100 / self.speed_count)
        else:
            return
        self.async_write_ha_state()

    @callback
    def _remote_changed(self, _event) -> None:
        self.async_write_ha_state()

    @property
    def percentage(self) -> int | None:
        return self._attr_percentage

    @property
    def is_on(self) -> bool | None:
        return None if self._attr_percentage is None else self._attr_percentage > 0

    async def _async_send_speed_level(self, level: int) -> None:
        level = max(1, min(self.speed_count, level))
        await async_send(self.hass, self.runtime, device=self.runtime.fan_device,
                         command=f"speed_{level}")
        self._last_on_level = level
        self._attr_percentage = round(level * 100 / self.speed_count)
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage <= 0:
            await self.async_turn_off()
            return
        level = _percentage_to_level(percentage, self.speed_count)
        await self._async_send_speed_level(level)

    async def async_turn_on(self, percentage: int | None = None,
                            preset_mode: str | None = None, **kwargs) -> None:
        if preset_mode is not None:
            raise ServiceValidationError("This fan has no preset modes")
        if percentage is not None:
            await self.async_set_percentage(percentage)
            return
        await self._async_send_speed_level(self._last_on_level or 1)

    async def async_turn_off(self, **kwargs) -> None:
        await async_send(self.hass, self.runtime, device=self.runtime.fan_device,
                         command="turn_off")
        self._attr_percentage = 0
        self.async_write_ha_state()
