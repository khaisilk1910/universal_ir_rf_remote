"""Isolated API-contract tests using tiny stand-ins for Home Assistant."""

from __future__ import annotations

from enum import Enum
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1] / "custom_components" / "universal_ir_rf_remote"


def get_integration(monkeypatch):
    def module(name):
        mod = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    module("homeassistant")
    module("voluptuous")
    module("homeassistant.helpers")
    module("homeassistant.helpers.dispatcher").async_dispatcher_send = lambda *args: None
    core = module("homeassistant.core")
    core.HomeAssistant = object
    core.ServiceCall = object
    core.callback = lambda fn: fn
    conf = module("homeassistant.config_entries")

    class ConfigEntry:
        def __class_getitem__(cls, item):
            return cls

    class ConfigEntryState(Enum):
        LOADED = "loaded"
        NOT_LOADED = "not_loaded"

    conf.ConfigEntry = ConfigEntry
    conf.ConfigEntryState = ConfigEntryState

    class Platform(Enum):
        FAN = "fan"
        SENSOR = "sensor"

    module("homeassistant.const").Platform = Platform

    class ServiceValidationError(Exception):
        pass

    error_mod = module("homeassistant.exceptions")
    error_mod.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    error_mod.ServiceValidationError = ServiceValidationError

    cv = module("homeassistant.helpers.config_validation")
    cv.config_entry_only_config_schema = lambda domain: {}
    module("homeassistant.helpers.start").async_at_started = lambda hass, fn: lambda: None
    module("homeassistant.helpers.typing").ConfigType = dict
    package = module("universal_ir_rf_remote")
    package.__path__ = [str(ROOT)]
    for name in ("universal_ir_rf_remote.const", "universal_ir_rf_remote.library"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    spec = importlib.util.spec_from_file_location(
        "universal_ir_rf_remote", ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "universal_ir_rf_remote", mod)
    spec.loader.exec_module(mod)
    return mod, conf


class FakeHass:
    def __init__(self, tmp_path):
        self.config = SimpleNamespace(path=lambda *args: str(tmp_path.joinpath(*args)), language="vi")
        self.calls = []
        self.services = SimpleNamespace(async_call=self.call)
        self.config_entries = SimpleNamespace(async_entries=lambda d: [])
        self.io_calls = 0

    async def call(self, domain, name, payload, **kwargs):
        self.calls.append((domain, name, payload, kwargs))

    async def async_add_executor_job(self, *_):
        self.io_calls += 1


@pytest.mark.asyncio
async def test_learn_api_no_unverified_frequency_payload(tmp_path, monkeypatch):
    mod, _ = get_integration(monkeypatch)
    hass = FakeHass(tmp_path)
    entry = SimpleNamespace(
        options={"rf_frequency_entity": "number.my_hub_frequency"},
        data={"remote_entity": "remote.hub"},
    )
    runtime = mod.RemoteRuntime(library=None, entry=entry)
    await mod.async_learn(
        hass, runtime, device="ceiling_fan", command="speed_3", command_type="rf_315",
    )
    assert hass.calls[0][:3] == (
        "number", "set_value", {"entity_id": "number.my_hub_frequency", "value": 315.0}
    )
    assert hass.calls[1][2] == {
        "entity_id": "remote.hub", "device": "ceiling_fan",
        "command": "speed_3", "command_type": "rf",
    }
    hass.calls.clear()
    await mod.async_learn(hass, runtime, device="tv", command="power", command_type="ir")
    assert len(hass.calls) == 1
    assert "command_type" not in hass.calls[0][2]


@pytest.mark.asyncio
async def test_no_io_in_setup_and_remote_command_repeats(tmp_path, monkeypatch):
    mod, conf = get_integration(monkeypatch)
    hass = FakeHass(tmp_path)
    forwarded = []

    async def forward(entry, platforms):
        forwarded.extend(platforms)

    hass.config_entries.async_forward_entry_setups = forward
    entry = SimpleNamespace(
        entry_id="some_entry", options={}, data={"remote_entity": "remote.hub"},
        add_update_listener=lambda fn: (lambda: None),
        async_on_unload=lambda unsub: None,
        async_create_background_task=lambda *args: None,
    )
    assert await mod.async_setup_entry(hass, entry) is True
    assert len(forwarded) == 2
    assert hass.io_calls == 0
    await mod.async_send(
        hass, entry.runtime_data, device="fan", command="speed_1",
    )
    assert hass.calls[-1][2] == {
        "entity_id": "remote.hub", "device": "fan", "command": "speed_1",
        "num_repeats": 1,
    }
    assert hass.calls[-1][3]["blocking"] is True


def _entry(mod, conf, entry_id, remote):
    data = {"remote_entity": remote}
    item = SimpleNamespace(entry_id=entry_id, data=data, options={},
                           state=conf.ConfigEntryState.LOADED)
    item.runtime_data = mod.RemoteRuntime(library=None, entry=item)
    return item


def test_multi_remote_resolution_requires_explicit_target(tmp_path, monkeypatch):
    mod, conf = get_integration(monkeypatch)
    hass = FakeHass(tmp_path)
    tv = _entry(mod, conf, "entry_tv", "remote.broadlink")
    rf = _entry(mod, conf, "entry_rf", "remote.tuya")
    hass.config_entries.async_entries = lambda domain: [tv, rf]

    with pytest.raises(Exception, match="Select exactly one"):
        mod._runtime_for_service(hass, {})
    assert mod._runtime_for_service(hass, {"remote_entity": "remote.tuya"}) is rf.runtime_data
    assert mod._runtime_for_service(hass, {"config_entry_id": "entry_tv"}) is tv.runtime_data
    with pytest.raises(Exception, match="does not belong"):
        mod._runtime_for_service(hass, {
            "config_entry_id": "entry_tv", "remote_entity": "remote.tuya",
        })
    with pytest.raises(Exception, match="Select exactly one"):
        mod._runtime_for_service(hass, {"remote_entity": "remote.missing"})


def test_fan_opt_in_by_default(tmp_path, monkeypatch):
    mod, conf = get_integration(monkeypatch)
    new = _entry(mod, conf, "new", "remote.broadlink")
    assert new.runtime_data.enable_fan is False
    new.options = {"enable_fan": True, "fan_speed_count": 3, "fan_device": "fan_room"}
    assert new.runtime_data.enable_fan is True
    assert new.runtime_data.fan_speed_count == 3
    assert new.runtime_data.fan_device == "fan_room"


@pytest.mark.asyncio
async def test_generic_ir_rf_actions_and_inline_without_device(tmp_path, monkeypatch):
    mod, conf = get_integration(monkeypatch)
    hass = FakeHass(tmp_path)
    entry = _entry(mod, conf, "broadlink", "remote.broadlink")
    await mod.async_learn(hass, entry.runtime_data, device="tv", command="on", command_type="ir")
    assert hass.calls[-1][2] == {
        "entity_id": "remote.broadlink", "device": "tv", "command": "on",
    }
    await mod.async_learn(
        hass, entry.runtime_data, device="blind", command="open",
        command_type="rf", alternative=True,
    )
    assert hass.calls[-1][2]["command_type"] == "rf"
    assert hass.calls[-1][2]["alternative"] is True
    await mod.async_send(
        hass, entry.runtime_data, command="b64:abcdef", delay_secs=1.2,
    )
    assert hass.calls[-1][2] == {
        "entity_id": "remote.broadlink", "command": "b64:abcdef",
        "num_repeats": 1, "delay_secs": 1.2,
    }


@pytest.mark.asyncio
async def test_setup_storage_paths_do_not_collide(tmp_path, monkeypatch):
    mod, conf = get_integration(monkeypatch)
    hass = FakeHass(tmp_path)

    async def forward(entry, platforms):
        assert len(platforms) == 2
    hass.config_entries.async_forward_entry_setups = forward
    entries = []
    for entry_id, data in [
        ("new_living", {"remote_entity": "remote.living_room"}),
        ("new_tv", {"remote_entity": "remote.broadlink"}),
        ("new_rf", {"remote_entity": "remote.tuya"}),
    ]:
        entry = SimpleNamespace(
            entry_id=entry_id, data=data, options={},
            add_update_listener=lambda fn: (lambda: None),
            async_on_unload=lambda unsub: None,
            async_create_background_task=lambda *args: None,
        )
        assert await mod.async_setup_entry(hass, entry)
        entries.append(entry)
    assert hass.io_calls == 0
    paths = [str(entry.runtime_data.library.path) for entry in entries]
    assert len(set(paths)) == 3
    assert paths[0].endswith("universal_ir_rf_remote_library_new_living.json")
    assert paths[1].endswith("universal_ir_rf_remote_library_new_tv.json")


@pytest.mark.asyncio
async def test_deletion_preserves_metadata_on_provider_error(tmp_path, monkeypatch):
    mod, conf = get_integration(monkeypatch)
    hass = FakeHass(tmp_path)
    class Library:
        def __init__(self):
            self.deleted = []
        async def async_remove(self, device, command):
            self.deleted.append((device, command))
    library = Library()
    entry = _entry(mod, conf, "my_entry", "remote.living_room")
    entry.runtime_data.library = library

    async def failed_call(*args, **kwargs):
        raise RuntimeError("provider does not support delete")
    hass.services.async_call = failed_call
    with pytest.raises(RuntimeError):
        await mod.async_delete(hass, entry.runtime_data, device="tv", command="off")
    assert not library.deleted
    await mod.async_delete(hass, entry.runtime_data,
                           device="tv", command="off", local_only=True)
    assert library.deleted == [("tv", "off")]


@pytest.mark.asyncio
async def test_service_defaults_to_ir_for_all_remotes(tmp_path, monkeypatch):
    mod, conf = get_integration(monkeypatch)
    hass = FakeHass(tmp_path)
    imports = sys.modules["voluptuous"]
    imports.Optional = lambda key, **kwargs: key
    imports.Required = lambda key, **kwargs: key
    imports.Schema = lambda schema: schema
    imports.All = lambda *args: args[0]
    imports.Length = lambda **kwargs: object()
    imports.Range = lambda **kwargs: object()
    imports.In = lambda allowed: object()
    imports.Coerce = lambda arg: object()
    cv = sys.modules["homeassistant.helpers.config_validation"]
    cv.string = str
    cv.entity_id = str
    cv.boolean = bool
    actions = {}
    hass.services.async_register = lambda domain, action, handler, schema: actions.setdefault(action, handler)
    mod._register_services(hass)

    class Library:
        def __init__(self):
            self.recorded = []
        async def async_record(self, device, command, kind):
            self.recorded.append((device, command, kind))

    entries = [
        _entry(mod, conf, "living_room", "remote.living_room"),
        _entry(mod, conf, "generic", "remote.broadlink"),
    ]
    for entry in entries:
        entry.runtime_data.library = Library()
    hass.config_entries.async_entries = lambda domain: entries
    for entry in entries:
        expected = "ir"
        await actions["learn_command"](SimpleNamespace(
            data={"remote_entity": entry.runtime_data.remote_entity,
                  "device": "tv", "command": "power", "alternative": False},
            context=None,
        ))
        assert entry.runtime_data.library.recorded == [("tv", "power", expected)]
        assert ("command_type" in hass.calls[-1][2]) is (expected == "rf")


@pytest.mark.asyncio
async def test_new_config_flow_prevents_duplicate_remote(tmp_path, monkeypatch):
    mod, conf = get_integration(monkeypatch)
    from importlib import util

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            return super().__init_subclass__()
        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}
        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

    conf.ConfigFlow = ConfigFlow
    conf.OptionsFlow = type("OptionsFlow", (), {})
    vol = sys.modules["voluptuous"]
    vol.Schema = lambda val: val
    vol.Required = lambda key, **kwargs: key
    selectors = ModuleType("homeassistant.helpers.selector")
    selectors.EntitySelectorConfig = lambda **kwargs: kwargs
    selectors.EntitySelector = lambda cfg: cfg
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.selector", selectors)
    spec = util.spec_from_file_location(
        "universal_ir_rf_remote.config_flow", ROOT / "config_flow.py"
    )
    flowmod = util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "universal_ir_rf_remote.config_flow", flowmod)
    spec.loader.exec_module(flowmod)
    previous = _entry(mod, conf, "old", "remote.broadlink")
    hass = FakeHass(tmp_path)
    hass.config_entries.async_entries = lambda domain: [previous]
    hass.states = SimpleNamespace(get=lambda entity: SimpleNamespace(name=entity)
                                   if entity != "remote.missing" else None)
    flow = flowmod.UniversalRemoteConfigFlow()
    flow.hass = hass
    created = await flow.async_step_user({"remote_entity": "remote.tuya"})
    assert created["data"] == {"remote_entity": "remote.tuya"}
    duplicate = await flow.async_step_user({"remote_entity": "remote.broadlink"})
    assert duplicate["errors"] == {"remote_entity": "already_configured"}
    missing = await flow.async_step_user({"remote_entity": "remote.missing"})
    assert missing["errors"] == {"remote_entity": "remote_missing"}
