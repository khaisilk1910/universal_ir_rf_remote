"""Small isolated behavioral tests, runnable without the HA installation."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1] / "custom_components" / "universal_ir_rf_remote"


def import_library(monkeypatch):
    """Supply only the Home Assistant surfaces actually used by library.py."""
    for name in (
        "homeassistant", "homeassistant.core", "homeassistant.exceptions",
        "homeassistant.helpers", "homeassistant.helpers.dispatcher",
        "universal_ir_rf_remote",
    ):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    sys.modules["homeassistant.core"].HomeAssistant = object
    sys.modules["homeassistant.exceptions"].HomeAssistantError = type(
        "HomeAssistantError", (Exception,), {}
    )
    signals = []
    sys.modules["homeassistant.helpers.dispatcher"].async_dispatcher_send = (
        lambda hass, signal: signals.append(signal)
    )
    package = sys.modules["universal_ir_rf_remote"]
    package.__path__ = [str(ROOT)]
    # `library` relative imports `const`, let the interpreter resolve it.
    for name in ("universal_ir_rf_remote.const", "universal_ir_rf_remote.library"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    spec = importlib.util.spec_from_file_location("universal_ir_rf_remote.library", ROOT / "library.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "universal_ir_rf_remote.library", mod)
    spec.loader.exec_module(mod)
    return mod, signals


class FakeHass:
    def __init__(self, config_dir):
        self.config = SimpleNamespace(path=lambda *args: str(config_dir.joinpath(*args)))
        self.io_calls = 0

    async def async_add_executor_job(self, fn, *args):
        self.io_calls += 1
        return await asyncio.to_thread(fn, *args)


@pytest.mark.asyncio
async def test_defers_file_io_and_reads_existing_json_format(tmp_path, monkeypatch):
    mod, signals = import_library(monkeypatch)
    path = tmp_path / ".storage" / "universal_ir_rf_remote_library.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"fan": {"speed_1": {"type": "RF (315/433)"}}}))
    hass = FakeHass(tmp_path)
    library = mod.CodeLibrary(hass)
    assert hass.io_calls == 0
    assert library.command_count is None
    await library.async_load()
    assert hass.io_calls == 1
    assert library.command_count == 1
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_atomic_persistence_and_concurrent_mutations(tmp_path, monkeypatch):
    mod, signals = import_library(monkeypatch)
    hass = FakeHass(tmp_path)
    library = mod.CodeLibrary(hass)
    await asyncio.gather(*(
        library.async_record("fan", f"speed_{x}", "rf_433") for x in range(1, 7)
    ))
    assert library.command_count == 6
    assert set(json.loads(library.path.read_text())["fan"]) == {
        f"speed_{x}" for x in range(1, 7)
    }
    assert not list(library.path.parent.glob("*.tmp"))
    await library.async_remove("fan", "speed_1")
    assert library.command_count == 5
    await library.async_remove("fan", "does_not_exist")
    assert library.command_count == 5


@pytest.mark.asyncio
async def test_corrupted_file_is_preserved(tmp_path, monkeypatch):
    mod, _ = import_library(monkeypatch)
    library = mod.CodeLibrary(FakeHass(tmp_path))
    library.path.parent.mkdir()
    library.path.write_text("{not valid", encoding="utf-8")
    with pytest.raises(Exception, match="original data preserved"):
        await library.async_record("fan", "speed_1", "rf")
    assert library.path.read_text() == "{not valid"


@pytest.mark.asyncio
async def test_multiple_catalogs_are_isolated(tmp_path, monkeypatch):
    mod, signals = import_library(monkeypatch)
    hass = FakeHass(tmp_path)
    a = mod.CodeLibrary(hass, filename="universal_ir_rf_remote_library_first.json", signal="first")
    b = mod.CodeLibrary(hass, filename="universal_ir_rf_remote_library_second.json", signal="second")
    assert hass.io_calls == 0
    await asyncio.gather(
        a.async_record("tv", "power", "ir"),
        b.async_record("blinds", "up", "rf"),
    )
    assert a.command_count == 1 and b.command_count == 1
    assert a.codes == {"tv": a.codes["tv"]}
    assert b.codes == {"blinds": b.codes["blinds"]}
    assert a.path != b.path
    assert signals.count("first") == 1
    assert signals.count("second") == 1


@pytest.mark.asyncio
async def test_failed_atomic_write_keeps_memory_unchanged(tmp_path, monkeypatch):
    mod, _ = import_library(monkeypatch)
    library = mod.CodeLibrary(FakeHass(tmp_path))
    await library.async_record("tv", "power", "ir")
    original = library.path.read_bytes()
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(mod, "_write_library", fail)
    with pytest.raises(Exception, match="Cannot save"):
        await library.async_record("tv", "vol_up", "ir")
    assert library.path.read_bytes() == original
    assert library.command_count == 1
