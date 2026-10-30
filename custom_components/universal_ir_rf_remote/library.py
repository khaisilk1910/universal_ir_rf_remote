"""Versioned, atomic, per-remote virtual appliance and command library.

Version 1 (flat device/command map) is read without modifying the source file.
Version 2 preserves immutable IDs and provider command mappings across renames.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN, LIBRARY_FILE, SIGNAL_LIBRARY_UPDATED, APPLIANCE_KINDS,
    FAN_APPLIANCE_KINDS,
)

_LOGGER = logging.getLogger(__name__)


def _stable_id(kind: str, value: str) -> str:
    return uuid5(NAMESPACE_URL, f"{DOMAIN}/{kind}/{value}").hex


def validate_raw_code(code: str) -> str:
    """Accept a Broadlink Base64 payload, with or without its b64: prefix."""
    candidate = code.strip()
    if candidate.lower().startswith("b64:"):
        candidate = candidate[4:]
    try:
        decoded = base64.b64decode(candidate, validate=True)
    except (ValueError, binascii.Error) as err:
        raise ValueError("Invalid Base64 code") from err
    if not 16 <= len(decoded) <= 32768:
        raise ValueError("Base64 code must contain 16 to 32768 bytes")
    return f"b64:{base64.b64encode(decoded).decode('ascii')}"


def _read_library(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 2, "devices": {}}
    with path.open(encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, dict):
        raise ValueError("Library root must be an object")
    if raw.get("version") == 2:
        devices = raw.get("devices")
        if not isinstance(devices, dict):
            raise ValueError("Library v2 devices must be an object")
        for dev_id, dev in devices.items():
            if (not isinstance(dev_id, str) or not isinstance(dev, dict)
                    or not isinstance(dev.get("name"), str)
                    or not isinstance(dev.get("provider_device"), str)
                    or not isinstance(dev.get("commands"), dict)):
                raise ValueError("Invalid device record")
            for label, command in dev["commands"].items():
                if not isinstance(label, str) or not isinstance(command, dict):
                    raise ValueError("Invalid command record")
        return raw
    if "version" in raw:
        raise ValueError("Unsupported library format version")
    # Legacy format: {"fan": {"speed_1": {"type":"rf"}}}.
    devices: dict[str, dict] = {}
    for name, commands in raw.items():
        if not isinstance(name, str) or not isinstance(commands, dict):
            continue
        dev_id = _stable_id("device", name)
        converted = {}
        for command, meta in commands.items():
            if not isinstance(command, str):
                continue
            record = dict(meta) if isinstance(meta, dict) else {"type": "rf"}
            record.setdefault("id", _stable_id("command", f"{name}/{command}"))
            record.setdefault("provider_command", command)
            converted[command] = record
        devices[dev_id] = {
            "name": name, "provider_device": name,
            "kind": "generic", "commands": converted,
        }
    return {"version": 2, "devices": devices}


def _write_library(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as file:
            temp_path = file.name
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.unlink(temp_path)


class CodeLibrary:
    """Metadata collection; disk access only on demand or after HA startup."""

    def __init__(self, hass: HomeAssistant, *, filename: str = LIBRARY_FILE,
                 signal: str = SIGNAL_LIBRARY_UPDATED) -> None:
        self.hass = hass
        self.path = Path(hass.config.path(".storage", filename))
        self.signal = signal
        self._lock = asyncio.Lock()
        self.devices: dict[str, dict] = {}
        self.loaded = False

    @property
    def codes(self) -> dict[str, dict[str, dict]]:
        """Compatibility projection for the existing options flow and tests."""
        return {dev["name"]: dev["commands"] for dev in self.devices.values()}

    async def _load_if_needed(self) -> None:
        if self.loaded:
            return
        try:
            data = await self.hass.async_add_executor_job(_read_library, self.path)
        except (OSError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.error("Cannot load remote metadata at %s: %s", self.path, err)
            raise HomeAssistantError("Cannot read remote library; original data preserved") from err
        self.devices = data["devices"]
        self.loaded = True

    async def async_load(self, *, force: bool = False) -> dict:
        async with self._lock:
            previously_loaded = self.loaded
            if force:
                self.loaded = False
            await self._load_if_needed()
            if not previously_loaded or force:
                async_dispatcher_send(self.hass, self.signal)
            return self.codes

    async def _write(self, devices: dict[str, dict]) -> None:
        try:
            await self.hass.async_add_executor_job(
                _write_library, self.path, {"version": 2, "devices": devices}
            )
        except OSError as err:
            raise HomeAssistantError("Cannot save remote library") from err
        self.devices = devices
        async_dispatcher_send(self.hass, self.signal)

    def device_by_name(self, name: str) -> tuple[str, dict] | None:
        return next(((key, dev) for key, dev in self.devices.items()
                     if dev["name"].casefold() == name.casefold()), None)

    def _find(self, device: str) -> tuple[str, dict] | None:
        if device in self.devices:
            return device, self.devices[device]
        return self.device_by_name(device)

    async def async_create_device(self, name: str, *, kind: str = "generic",
                                  provider_device: str | None = None) -> str:
        name = name.strip()
        if not name or len(name) > 128 or kind not in APPLIANCE_KINDS:
            raise ValueError("Invalid device name or type")
        async with self._lock:
            await self._load_if_needed()
            if self.device_by_name(name):
                raise ValueError("A device with this name already exists")
            key = uuid4().hex
            devices = deepcopy(self.devices)
            devices[key] = {"name": name, "provider_device": (provider_device or name).strip(),
                            "kind": kind, "commands": {}}
            await self._write(devices)
            return key

    async def async_update_device(self, device: str, *, name: str,
                                  kind: str | None = None) -> None:
        name = name.strip()
        if not name or len(name) > 128:
            raise ValueError("Invalid device name")
        async with self._lock:
            await self._load_if_needed()
            found = self._find(device)
            if not found:
                raise ValueError("Device not found")
            key, existing = found
            other = self.device_by_name(name)
            if other and other[0] != key:
                raise ValueError("Device name already exists")
            if kind is not None and kind not in APPLIANCE_KINDS:
                raise ValueError("Invalid device type")
            if existing.get("fan") and kind is not None and kind not in FAN_APPLIANCE_KINDS:
                raise ValueError("Remove the fan mapping before changing appliance type")
            devices = deepcopy(self.devices)
            devices[key]["name"] = name
            if kind is not None:
                devices[key]["kind"] = kind
            await self._write(devices)

    async def async_delete_device(self, device: str) -> None:
        """Delete local grouping only; never silently erase Broadlink codes."""
        async with self._lock:
            await self._load_if_needed()
            found = self._find(device)
            if not found:
                raise ValueError("Device not found")
            devices = deepcopy(self.devices)
            del devices[found[0]]
            await self._write(devices)

    async def async_configure_fan(self, device: str, speed_ids: list[str],
                                  *, off_id: str | None = None) -> None:
        """Map a fan to existing signal IDs, never to mutable labels.

        The fan is a virtual appliance associated with this remote library;
        deleting its fan configuration does not delete its learned signals.
        """
        async with self._lock:
            await self._load_if_needed()
            found = self._find(device)
            if not found:
                raise ValueError("The selected appliance no longer exists")
            key, appliance = found
            if not isinstance(speed_ids, list) or not 1 <= len(speed_ids) <= 10:
                raise ValueError("Select between 1 and 10 fan speed commands")
            ids = {data.get("id") for data in appliance["commands"].values()}
            if (len(set(speed_ids)) != len(speed_ids)
                    or any(signal not in ids for signal in speed_ids)
                    or (off_id is not None and (off_id not in ids or off_id in speed_ids))):
                raise ValueError("Select distinct commands belonging to this appliance")
            updated = deepcopy(self.devices)
            updated[key]["kind"] = (appliance.get("kind")
                                     if appliance.get("kind") in FAN_APPLIANCE_KINDS else "fan")
            updated[key]["fan"] = {"speeds": list(speed_ids), "off": off_id}
            await self._write(updated)

    async def async_remove_fan(self, device: str) -> None:
        """Remove just the HA fan mapping, retaining all appliance commands."""
        async with self._lock:
            await self._load_if_needed()
            found = self._find(device)
            if not found or "fan" not in found[1]:
                raise ValueError("This appliance does not have a fan configuration")
            updated = deepcopy(self.devices)
            updated[found[0]].pop("fan", None)
            await self._write(updated)

    async def async_record(self, device: str, command: str, command_type: str,
                           *, raw_code: str | None = None,
                           provider_command: str | None = None,
                           verified: bool = True) -> None:
        device = device.strip()
        command = command.strip()
        if not device or len(device) > 128 or not command or len(command) > 128:
            raise ValueError("Invalid command name")
        if raw_code:
            raw_code = validate_raw_code(raw_code)
        async with self._lock:
            await self._load_if_needed()
            devices = deepcopy(self.devices)
            found = self._find(device)
            if found:
                key, original = found
            else:
                key = uuid4().hex
                original = {"name": device, "provider_device": device,
                            "kind": "generic", "commands": {}}
                devices[key] = original
            if command in devices[key]["commands"]:
                old = devices[key]["commands"][command]
                command_id = old.get("id", uuid4().hex)
                provider_name = provider_command or old.get("provider_command", command)
            else:
                command_id = uuid4().hex
                provider_name = provider_command or command
            devices[key]["commands"][command] = {
                "id": command_id, "type": command_type,
                "verified": verified,
                "provider_command": provider_name,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                **({"raw_code": raw_code} if raw_code else {}),
            }
            await self._write(devices)

    async def async_import_codes(self, device: str, codes: dict[str, str],
                                 *, command_type: str = "rf") -> int:
        """Import multiple raw codes transactionally, after validating all of them."""
        device = device.strip()
        if not device or len(device) > 128:
            raise ValueError("Invalid device name")
        if not isinstance(codes, dict) or not (1 <= len(codes) <= 100):
            raise ValueError("Provide 1 to 100 named codes")
        checked = {}
        for label, code in codes.items():
            if not isinstance(label, str) or not label.strip() or len(label) > 128:
                raise ValueError("Invalid command label")
            if not isinstance(code, str):
                raise ValueError("Command code must be a Base64 string")
            checked[label.strip()] = validate_raw_code(code)
        if len(checked) != len(codes):
            raise ValueError("Duplicate command labels")
        async with self._lock:
            await self._load_if_needed()
            devices = deepcopy(self.devices)
            found = self._find(device)
            if found is None:
                key = uuid4().hex
                devices[key] = {"name": device, "provider_device": device,
                                "kind": "generic", "commands": {}}
            else:
                key = found[0]
            commands = devices[key]["commands"]
            for label, raw_code in checked.items():
                previous = commands.get(label, {})
                commands[label] = {
                    "id": previous.get("id", uuid4().hex),
                    "type": command_type,
                    "provider_command": previous.get("provider_command", label),
                    "raw_code": raw_code,
                    "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            await self._write(devices)
        return len(checked)

    async def async_update_command(self, device: str, command: str, *,
                                   name: str, raw_code: str | None = None) -> None:
        name = name.strip()
        if not name or len(name) > 128:
            raise ValueError("Invalid command name")
        if raw_code:
            raw_code = validate_raw_code(raw_code)
        async with self._lock:
            await self._load_if_needed()
            found = self._find(device)
            if not found or command not in found[1]["commands"]:
                raise ValueError("Command not found")
            key, dev = found
            if name != command and name in dev["commands"]:
                raise ValueError("Command name already exists")
            devices = deepcopy(self.devices)
            meta = devices[key]["commands"].pop(command)
            if raw_code:
                meta["raw_code"] = raw_code
            devices[key]["commands"][name] = meta
            await self._write(devices)

    async def async_remove(self, device: str, command: str) -> None:
        async with self._lock:
            await self._load_if_needed()
            found = self._find(device)
            if not found or command not in found[1]["commands"]:
                return
            devices = deepcopy(self.devices)
            removed_id = devices[found[0]]["commands"][command].get("id")
            del devices[found[0]]["commands"][command]
            fan = devices[found[0]].get("fan")
            if fan and removed_id is not None:
                fan["speeds"] = [item for item in fan["speeds"] if item != removed_id]
                if fan.get("off") == removed_id:
                    fan["off"] = None
                if not fan["speeds"]:
                    devices[found[0]].pop("fan", None)
            # Keep named devices even when empty.
            await self._write(devices)

    async def async_resolve(self, device: str, command: str) -> dict | None:
        await self.async_load()
        found = self._find(device)
        if not found:
            return None
        meta = found[1]["commands"].get(command)
        if meta is None:
            return None
        return {"device_id": found[0], "provider_device": found[1]["provider_device"],
                "provider_command": meta.get("provider_command", command), **meta}

    @property
    def command_count(self) -> int | None:
        if not self.loaded:
            return None
        return sum(len(dev["commands"]) for dev in self.devices.values())
