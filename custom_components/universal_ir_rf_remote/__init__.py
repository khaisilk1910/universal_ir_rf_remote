"""Generic IR/RF metadata and UI manager for existing Home Assistant remotes.

Never own the hardware connection. All signal I/O is delegated to the configured
remote entity using standard Home Assistant actions.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.device_registry import DeviceEntry, async_get as async_get_device_registry
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, SIGNAL_LIBRARY_UPDATED, SIGNAL_COMMAND_SENT, CONF_ENTRY_ID,
    CONF_REMOTE_ENTITY, CONF_ENABLE_FAN,
    CONF_FAN_DEVICE, CONF_FAN_SPEED_COUNT, CONF_RF_FREQUENCY_ENTITY,
    DEFAULT_FAN_DEVICE, DEFAULT_FAN_SPEED_COUNT, DEFAULT_REPEATS,
    APPLIANCE_KINDS,
)
from .library import CodeLibrary

_LOGGER = logging.getLogger(__name__)
PLATFORMS = (Platform.FAN, Platform.SENSOR, Platform.BUTTON, Platform.SELECT)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class RemoteRuntime:
    """Per-config-entry state; no disk or network I/O in construction."""

    library: CodeLibrary
    entry: ConfigEntry

    def option(self, name: str, default):
        return self.entry.options.get(name, self.entry.data.get(name, default))

    @property
    def command_signal(self) -> str:
        """Notify entities in this config entry only; never cross remote hubs."""
        return f"{SIGNAL_COMMAND_SENT}_{self.entry.entry_id}"

    @property
    def remote_entity(self) -> str:
        return self.option(CONF_REMOTE_ENTITY, "")

    @property
    def enable_fan(self) -> bool:
        return bool(self.option(CONF_ENABLE_FAN, False))

    @property
    def fan_device(self) -> str:
        return self.option(CONF_FAN_DEVICE, DEFAULT_FAN_DEVICE)

    @property
    def fan_speed_count(self) -> int:
        return int(self.option(CONF_FAN_SPEED_COUNT, DEFAULT_FAN_SPEED_COUNT))

    @property
    def rf_frequency_entity(self) -> str | None:
        return self.option(CONF_RF_FREQUENCY_ENTITY, "") or None


ManagerConfigEntry = ConfigEntry[RemoteRuntime]


def _runtime_for_service(hass: HomeAssistant, data: dict) -> RemoteRuntime:
    """Resolve explicit target; refuse ambiguous requests on multi-hub systems."""
    loaded = [
        entry for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    entry_id = data.get(CONF_ENTRY_ID)
    remote_entity = data.get(CONF_REMOTE_ENTITY)
    if entry_id:
        selected = [entry for entry in loaded if entry.entry_id == entry_id]
    elif remote_entity:
        selected = [
            entry for entry in loaded
            if entry.runtime_data.remote_entity == remote_entity
        ]
    else:
        # Compatibility with automations written before multi-remote support.
        selected = loaded if len(loaded) == 1 else []
    if len(selected) != 1:
        raise ServiceValidationError(
            "Select exactly one configured remote with config_entry_id or "
            "remote_entity (or configure a single remote)"
        )
    runtime = selected[0].runtime_data
    if remote_entity and runtime.remote_entity != remote_entity:
        raise ServiceValidationError("The remote entity does not belong to the selected entry")
    return runtime


async def async_prepare_frequency(hass: HomeAssistant, runtime: RemoteRuntime, command_type: str) -> None:
    """Never infer RF hardware bands or datapoint identifiers."""
    if command_type not in ("rf_315", "rf_433"):
        return
    if not runtime.rf_frequency_entity:
        raise ServiceValidationError(
            "315/433 band selection requires a supported frequency number entity. "
            "For Broadlink select RF, not RF 315/433; Broadlink scans the band automatically."
        )
    frequency = 315.0 if command_type == "rf_315" else 433.92
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": runtime.rf_frequency_entity, "value": frequency},
        blocking=True,
    )


async def async_learn(
    hass: HomeAssistant, runtime: RemoteRuntime, *,
    device: str, command: str, command_type: str = "ir",
    alternative: bool = False, context=None,
) -> None:
    """Let provider learn/store the real waveform; metadata saved separately."""
    await async_prepare_frequency(hass, runtime, command_type)
    # A friendly appliance name may differ from the provider's immutable lookup key.
    if runtime.library is not None and hasattr(runtime.library, "async_load"):
        await runtime.library.async_load()
        matched = runtime.library._find(device)
        if matched:
            # Friendly labels can be renamed without renaming provider keys.
            # Relearning a saved label must replace the *original* provider
            # command, not silently create a second unrelated code.
            saved = matched[1]["commands"].get(command)
            if saved:
                command = saved.get("provider_command", command)
            device = matched[1]["provider_device"]
    payload = {
        "entity_id": runtime.remote_entity, "device": device, "command": command,
    }
    if command_type.startswith("rf"):
        payload["command_type"] = "rf"
    if alternative:
        payload["alternative"] = True
    await hass.services.async_call(
        "remote", "learn_command", payload, blocking=True, context=context,
    )


async def async_send(
    hass: HomeAssistant, runtime: RemoteRuntime, *,
    command: str, device: str | None = None, repeats: int = DEFAULT_REPEATS,
    delay_secs: float | None = None, context=None,
) -> None:
    """Send a command and notify local entities *only if* the provider succeeds.

    A resolved device_id/command_id is stable across user-visible renames.
    Raw packets without a saved library mapping cannot identify a fan and must
    not change any other entity's state.
    """
    identity: tuple[str, str] | None = None
    if device and runtime.library is not None:
        saved = await runtime.library.async_resolve(device, command)
        if saved is not None:
            if saved.get("device_id") and saved.get("id"):
                identity = (saved["device_id"], saved["id"])
            if saved.get("raw_code"):
                # Broadlink supports b64: raw packets without a device key.
                command = saved["raw_code"]
                device = None
            else:
                command = saved["provider_command"]
                device = saved["provider_device"]
    payload = {
        "entity_id": runtime.remote_entity, "command": command,
        "num_repeats": repeats,
    }
    if device:
        payload["device"] = device
    if delay_secs is not None:
        payload["delay_secs"] = delay_secs
    await hass.services.async_call(
        "remote", "send_command", payload, blocking=True, context=context,
    )
    if identity is not None:
        # All send paths (buttons, selects, fan, service, options) converge here.
        # No metadata writes, network requests, or other blocking I/O.
        async_dispatcher_send(hass, runtime.command_signal, *identity)


async def async_delete(
    hass: HomeAssistant, runtime: RemoteRuntime, *, device: str, command: str,
    local_only: bool = False, context=None,
) -> None:
    """Do not erase metadata if provider deletion fails."""
    command_in_provider = command
    device_in_provider = device
    if runtime.library is not None and hasattr(runtime.library, "async_resolve"):
        saved = await runtime.library.async_resolve(device, command)
        if saved:
            if saved.get("raw_code"):
                local_only = True  # Imported codes do not exist in provider storage.
            else:
                device_in_provider = saved["provider_device"]
                command_in_provider = saved["provider_command"]
    if not local_only:
        await hass.services.async_call(
            "remote", "delete_command",
            {"entity_id": runtime.remote_entity, "device": device_in_provider, "command": command_in_provider},
            blocking=True, context=context,
        )
    await runtime.library.async_remove(device, command)


@callback
def _register_services(hass: HomeAssistant) -> None:
    targets = {
        vol.Optional(CONF_ENTRY_ID): cv.string,
        vol.Optional(CONF_REMOTE_ENTITY): cv.entity_id,
    }
    command_fields = {
        vol.Required("command"): vol.All(cv.string, vol.Length(min=1, max=128)),
    }
    named_fields = {
        **command_fields,
        vol.Required("device"): vol.All(cv.string, vol.Length(min=1, max=128)),
    }

    async def learn(call: ServiceCall) -> None:
        runtime = _runtime_for_service(hass, call.data)
        # IR is the portable default; RF requires provider support.
        command_type = call.data.get("command_type", "ir")
        await async_learn(
            hass, runtime, device=call.data["device"],
            command=call.data["command"], command_type=command_type,
            alternative=call.data["alternative"], context=call.context,
        )
        # Broadlink can log a failed learn without propagating an exception.
        # Record an unverified entry so the user must still test it physically.
        await runtime.library.async_record(
            call.data["device"], call.data["command"], command_type, verified=False,
        )

    async def send(call: ServiceCall) -> None:
        await async_send(
            hass, _runtime_for_service(hass, call.data),
            command=call.data["command"], device=call.data.get("device"),
            repeats=call.data["repeats"],
            delay_secs=call.data.get("delay_secs"), context=call.context,
        )

    async def delete(call: ServiceCall) -> None:
        await async_delete(
            hass, _runtime_for_service(hass, call.data),
            device=call.data["device"], command=call.data["command"],
            local_only=call.data["local_only"], context=call.context,
        )

    async def refresh(call: ServiceCall) -> None:
        await _runtime_for_service(hass, call.data).library.async_load(force=True)

    async def create_device(call: ServiceCall) -> None:
        runtime = _runtime_for_service(hass, call.data)
        await runtime.library.async_create_device(
            call.data["name"], kind=call.data.get("kind", "generic"),
            provider_device=call.data.get("provider_device"),
        )

    async def rename_device(call: ServiceCall) -> None:
        runtime = _runtime_for_service(hass, call.data)
        await runtime.library.async_update_device(call.data["device"], name=call.data["name"])

    async def delete_device(call: ServiceCall) -> None:
        runtime = _runtime_for_service(hass, call.data)
        await async_remove_virtual_device(hass, runtime, call.data["device"])

    async def rename_command(call: ServiceCall) -> None:
        runtime = _runtime_for_service(hass, call.data)
        await runtime.library.async_update_command(
            call.data["device"], call.data["command"], name=call.data["name"],
        )

    async def import_code(call: ServiceCall) -> None:
        runtime = _runtime_for_service(hass, call.data)
        # Base64 is stored locally; never copy it to third-party storage files.
        await runtime.library.async_record(
            call.data["device"], call.data["command"],
            call.data.get("command_type", "rf"), raw_code=call.data["code"],
        )

    async def import_codes(call: ServiceCall) -> None:
        runtime = _runtime_for_service(hass, call.data)
        await runtime.library.async_import_codes(
            call.data["device"], call.data["codes"],
            command_type=call.data.get("command_type", "rf"),
        )

    device_fields = {**targets,
        vol.Required("device"): vol.All(cv.string, vol.Length(min=1, max=128)),
    }
    hass.services.async_register(
        DOMAIN, "create_device", create_device,
        schema=vol.Schema({**targets,
            vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=128)),
            vol.Optional("kind", default="generic"): vol.In(APPLIANCE_KINDS),
            vol.Optional("provider_device"): cv.string,
        }),
    )
    hass.services.async_register(
        DOMAIN, "rename_device", rename_device,
        schema=vol.Schema({**device_fields,
            vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=128)),
        }),
    )
    hass.services.async_register(
        DOMAIN, "delete_device", delete_device,
        schema=vol.Schema(device_fields),
    )
    hass.services.async_register(
        DOMAIN, "rename_command", rename_command,
        schema=vol.Schema({**device_fields, **command_fields,
            vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=128)),
        }),
    )
    hass.services.async_register(
        DOMAIN, "import_code", import_code,
        schema=vol.Schema({**device_fields, **command_fields,
            vol.Required("code"): vol.All(cv.string, vol.Length(min=20, max=50000)),
            vol.Optional("command_type", default="rf"): vol.In(("ir", "rf")),
        }),
    )

    hass.services.async_register(
        DOMAIN, "import_codes", import_codes,
        schema=vol.Schema({**device_fields,
            vol.Required("codes"): {cv.string: cv.string},
            vol.Optional("command_type", default="rf"): vol.In(("ir", "rf")),
        }),
    )
    hass.services.async_register(
        DOMAIN, "learn_command", learn,
        schema=vol.Schema({
            **named_fields, **targets,
            vol.Optional("command_type"):
                vol.In(("ir", "rf", "rf_315", "rf_433")),
            vol.Optional("alternative", default=False): cv.boolean,
        }),
    )
    hass.services.async_register(
        DOMAIN, "send_command", send,
        schema=vol.Schema({
            **command_fields, **targets,
            vol.Optional("device"): vol.All(cv.string, vol.Length(min=1, max=128)),
            vol.Optional("repeats", default=DEFAULT_REPEATS):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
            vol.Optional("delay_secs"): vol.All(vol.Coerce(float), vol.Range(min=0, max=30)),
        }),
    )
    hass.services.async_register(
        DOMAIN, "delete_command", delete,
        schema=vol.Schema({
            **named_fields, **targets,
            vol.Optional("local_only", default=False): cv.boolean,
        }),
    )
    hass.services.async_register(
        DOMAIN, "refresh_library", refresh,
        schema=vol.Schema(targets),
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Constant-time registration: no remote probing or filesystem access."""
    _register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ManagerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _remove_legacy_library_device(hass: HomeAssistant, entry: ManagerConfigEntry) -> None:
    """Prune the old synthetic manager device without deleting any appliances.

    Older releases linked all virtual appliances via a synthetic library parent.
    Home Assistant 2026.10 cascades parent/child removal in its device registry;
    unlinking first is essential for preserving the existing device IDs, areas,
    buttons and fan mappings. No library data is modified by this migration.
    """
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    devices = dr.async_get(hass)
    parent = devices.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id,
    )
    if parent is None:
        return  # No legacy manager registered for this config entry.

    # Detach every associated virtual appliance before pruning the parent.
    # Preserve the registry entry (and its user-chosen name, area and entity IDs).
    for appliance in tuple(dr.async_entries_for_config_entry(devices, entry.entry_id)):
        if appliance.id != parent.id and getattr(appliance, "via_device_id", None) == parent.id:
            devices.async_update_device(appliance.id, via_device_id=None)

    # Current HA also supports strict child devices. Never delete an old parent
    # if it still has real children: deleting it would cascade to those devices.
    if dr.async_entries_for_parent_device(devices, parent.id):
        _LOGGER.warning("Cannot prune legacy manager device %s: child devices remain", parent.id)
        return

    entities = er.async_get(hass)
    # Remove the obsolete hub-level 'Learned commands' sensor registry entry.
    obsolete = entities.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_learned_codes")
    if obsolete:
        entities.async_remove(obsolete)

    # Preserve any other user-customized legacy entities by unlinking rather
    # than deleting them. For example an old, still-enabled generic fan.
    for registered in tuple(er.async_entries_for_device(
        entities, parent.id, include_disabled_entities=True,
    )):
        entities.async_update_entity(registered.entity_id, device_id=None)

    devices.async_remove_device(parent.id)


async def async_setup_entry(hass: HomeAssistant, entry: ManagerConfigEntry) -> bool:
    """Create virtual entities; postpone metadata I/O until HA is started."""
    # entry_id comes from HA, but sanitize it anyway before using as a filename.
    safe_entry_id = re.sub(r"[^A-Za-z0-9_-]", "_", entry.entry_id)
    filename = f"{DOMAIN}_library_{safe_entry_id}.json"
    library = CodeLibrary(
        hass, filename=filename,
        signal=f"{SIGNAL_LIBRARY_UPDATED}_{entry.entry_id}",
    )
    entry.runtime_data = RemoteRuntime(library, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def load_after_startup() -> None:
        # Keep disk I/O outside startup. Only prune the old device after the
        # library has loaded and HA has forwarded all entity platforms.
        await library.async_load()
        try:
            _remove_legacy_library_device(hass, entry)
        except Exception:
            _LOGGER.exception("Could not migrate old library device for %s", entry.entry_id)

    @callback
    def after_started(_hass: HomeAssistant) -> None:
        entry.async_create_background_task(
            hass, load_after_startup(), f"{DOMAIN} {entry.entry_id} library load",
        )

    entry.async_on_unload(async_at_started(hass, after_started))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ManagerConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_virtual_device(hass: HomeAssistant, runtime: RemoteRuntime, device: str) -> None:
    """Remove library metadata and its registered HA virtual device."""
    await runtime.library.async_load()
    found = runtime.library._find(device)
    if found is None:
        raise ServiceValidationError("Virtual appliance not found")
    key = found[0]
    await runtime.library.async_delete_device(key)
    registry = async_get_device_registry(hass)
    registered = registry.async_get_device(identifiers={(DOMAIN, f"{runtime.entry.entry_id}_{key}")})
    if registered is not None:
        registry.async_remove_device(registered.id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ManagerConfigEntry, device_entry: DeviceEntry,
) -> bool:
    """Allow users to delete virtual appliances directly in HA Devices UI."""
    prefix = f"{entry.entry_id}_"
    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN or not identifier.startswith(prefix):
            continue
        key = identifier[len(prefix):]
        if key in entry.runtime_data.library.devices:
            await entry.runtime_data.library.async_delete_device(key)
            return True
    return False
