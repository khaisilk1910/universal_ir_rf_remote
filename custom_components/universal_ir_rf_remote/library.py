"""Generic per-remote, lazy and atomic metadata storage.

The underlying remote provider owns the actual learned RF/IR signal bytes.
This file stores only device/command names and metadata; never parse another
integration's private .storage records.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import LIBRARY_FILE, SIGNAL_LIBRARY_UPDATED

_LOGGER = logging.getLogger(__name__)


def _read_library(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        contents = json.load(file)
    if not isinstance(contents, dict):
        raise ValueError("Remote library root must be an object")
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for device, commands in contents.items():
        if not isinstance(device, str) or not isinstance(commands, dict):
            continue
        result[device] = {}
        for command, metadata in commands.items():
            if not isinstance(command, str):
                continue
            result[device][command] = (
                metadata if isinstance(metadata, dict) else {"type": "rf"}
            )
    return result


def _write_library(path: Path, data: dict) -> None:
    """Durably replace JSON without ever truncating the old file first."""
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
    """Independent per-remote metadata catalog, lazy to avoid startup I/O."""

    def __init__(self, hass: HomeAssistant, *, filename: str = LIBRARY_FILE,
                 signal: str = SIGNAL_LIBRARY_UPDATED) -> None:
        self.hass = hass
        self.path = Path(hass.config.path(".storage", filename))
        self.signal = signal
        self._lock = asyncio.Lock()
        self.codes: dict[str, dict[str, dict[str, Any]]] = {}
        self.loaded = False

    async def async_load(self, *, force: bool = False) -> dict:
        async with self._lock:
            if not self.loaded or force:
                try:
                    contents = await self.hass.async_add_executor_job(
                        _read_library, self.path
                    )
                except (OSError, ValueError, json.JSONDecodeError) as err:
                    _LOGGER.error("Could not read remote library %s: %s", self.path, err)
                    raise HomeAssistantError("Cannot read remote library; original data preserved") from err
                self.codes = contents
                self.loaded = True
                async_dispatcher_send(self.hass, self.signal)
            return self.codes

    async def async_record(self, device: str, command: str, command_type: str) -> None:
        async with self._lock:
            await self._load_if_needed()
            # Only replace the in-memory value once persistence succeeds.
            new_codes = {dev: dict(commands) for dev, commands in self.codes.items()}
            new_codes.setdefault(device, {})[command] = {
                "type": command_type,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            await self._write(new_codes)

    async def async_remove(self, device: str, command: str) -> None:
        async with self._lock:
            await self._load_if_needed()
            if command not in self.codes.get(device, {}):
                return
            new_codes = {dev: dict(commands) for dev, commands in self.codes.items()}
            del new_codes[device][command]
            if not new_codes[device]:
                del new_codes[device]
            await self._write(new_codes)

    async def _load_if_needed(self) -> None:
        # Called under _lock: do not recurse into async_load.
        if not self.loaded:
            try:
                self.codes = await self.hass.async_add_executor_job(_read_library, self.path)
            except (OSError, ValueError, json.JSONDecodeError) as err:
                raise HomeAssistantError("Cannot read remote library; original data preserved") from err
            self.loaded = True

    async def _write(self, updated: dict) -> None:
        try:
            await self.hass.async_add_executor_job(_write_library, self.path, updated)
        except OSError as err:
            raise HomeAssistantError("Cannot save remote library") from err
        self.codes = updated
        async_dispatcher_send(self.hass, self.signal)

    @property
    def command_count(self) -> int | None:
        if not self.loaded:
            return None
        return sum(map(len, self.codes.values()))
