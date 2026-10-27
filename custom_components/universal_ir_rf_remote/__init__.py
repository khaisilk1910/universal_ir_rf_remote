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
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, SIGNAL_LIBRARY_UPDATED, CONF_ENTRY_ID,
    CONF_REMOTE_ENTITY, CONF_ENABLE_FAN,
    CONF_FAN_DEVICE, CONF_FAN_SPEED_COUNT, CONF_RF_FREQUENCY_ENTITY,
    DEFAULT_FAN_DEVICE, DEFAULT_FAN_SPEED_COUNT, DEFAULT_REPEATS,
)
from .library import CodeLibrary

_LOGGER = logging.getLogger(__name__)
PLATFORMS = (Platform.FAN, Platform.SENSOR)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class RemoteRuntime:
    """Per-config-entry state; no disk or network I/O in construction."""

    library: CodeLibrary
    entry: ConfigEntry

    def option(self, name: str, default):
        return self.entry.options.get(name, self.entry.data.get(name, default))

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
    if command_type not in ("rf_315", "rf_433") or not runtime.rf_frequency_entity:
        return
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
    """Send named commands or provider-supported raw commands."""
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


async def async_delete(
    hass: HomeAssistant, runtime: RemoteRuntime, *, device: str, command: str,
    local_only: bool = False, context=None,
) -> None:
    """Do not erase metadata if provider deletion fails."""
    if not local_only:
        await hass.services.async_call(
            "remote", "delete_command",
            {"entity_id": runtime.remote_entity, "device": device, "command": command},
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
        await runtime.library.async_record(
            call.data["device"], call.data["command"], command_type,
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

    @callback
    def after_started(_hass: HomeAssistant) -> None:
        entry.async_create_background_task(
            hass, library.async_load(), f"{DOMAIN} {entry.entry_id} library load",
        )

    entry.async_on_unload(async_at_started(hass, after_started))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ManagerConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
