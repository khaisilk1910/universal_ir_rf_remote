"""Test optimistic fan conversion independently from Home Assistant installation."""

from __future__ import annotations

from enum import Flag, auto
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1] / "custom_components" / "universal_ir_rf_remote"


def import_fan(monkeypatch):
    def add(name):
        mod = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    add("homeassistant")
    add("homeassistant.components")
    fans = add("homeassistant.components.fan")

    class FanEntityFeature(Flag):
        SET_SPEED = auto()
        TURN_ON = auto()
        TURN_OFF = auto()

    class FanEntity:
        def async_write_ha_state(self):
            pass

        @property
        def speed_count(self):
            return self._attr_speed_count

    fans.FanEntity = FanEntity
    fans.FanEntityFeature = FanEntityFeature
    core = add("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda fn: fn
    add("homeassistant.helpers")
    add("homeassistant.helpers.device_registry").DeviceInfo = dict
    add("homeassistant.helpers.entity_platform").AddEntitiesCallback = object
    add("homeassistant.helpers.event").async_track_state_change_event = lambda *args: lambda: None
    parent = add("universal_ir_rf_remote")
    parent.__path__ = [str(ROOT)]
    parent.ManagerConfigEntry = object
    parent.RemoteRuntime = object
    calls = []

    async def send(hass, runtime, **kwargs):
        calls.append(kwargs)

    parent.async_send = send
    name = "universal_ir_rf_remote.fan"
    spec = importlib.util.spec_from_file_location(name, ROOT / "fan.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module, calls


@pytest.mark.asyncio
async def test_fan_sends_speed_and_off_with_one_repeat(tmp_path, monkeypatch):
    mod, calls = import_fan(monkeypatch)
    entry = SimpleNamespace(entry_id="entry1")
    runtime = SimpleNamespace(entry=entry, fan_device="ceiling_fan", fan_speed_count=6, remote_entity="remote.hub", enable_fan=True)
    fan = mod.GenericRemoteFan(runtime)
    fan.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _: SimpleNamespace(state="on")))
    assert fan.is_on is None
    await fan.async_set_percentage(34)
    assert calls[-1]["command"] == "speed_3"
    assert fan.percentage == 50
    assert fan.is_on is True
    await fan.async_set_percentage(0)
    assert calls[-1]["command"] == "turn_off"
    assert fan.percentage == 0
    assert fan.is_on is False
    await fan.async_turn_on()
    assert calls[-1]["command"] == "speed_6"
    assert fan.available is True
