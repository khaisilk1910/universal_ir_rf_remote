"""UI config and per-remote command management for IR/RF remote providers."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import RemoteRuntime, async_delete, async_learn, async_send
from .const import (
    DOMAIN, CONF_REMOTE_ENTITY, CONF_ENABLE_FAN,
    CONF_FAN_DEVICE, CONF_FAN_SPEED_COUNT, CONF_RF_FREQUENCY_ENTITY,
    DEFAULT_FAN_SPEED_COUNT, DEFAULT_REPEATS, DEFAULT_DEVICES, DEFAULT_COMMANDS,
)

_LOGGER = logging.getLogger(__name__)


def _entity_selector():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="remote"))


def _name_selector(names):
    return selector.SelectSelector(selector.SelectSelectorConfig(
        options=list(dict.fromkeys(names)), custom_value=True,
        mode=selector.SelectSelectorMode.DROPDOWN,
    ))


def _choice_selector(options, translation_key):
    return selector.SelectSelector(selector.SelectSelectorConfig(
        options=options, translation_key=translation_key,
        mode=selector.SelectSelectorMode.LIST,
    ))


def _duplicate(hass, remote: str, exclude_entry_id: str | None = None) -> bool:
    return any(
        entry.entry_id != exclude_entry_id and
        entry.options.get(CONF_REMOTE_ENTITY, entry.data.get(CONF_REMOTE_ENTITY)) == remote
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


class UniversalRemoteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Each selected remote entity gets a separate config entry and library."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            remote = user_input[CONF_REMOTE_ENTITY]
            if self.hass.states.get(remote) is None:
                errors[CONF_REMOTE_ENTITY] = "remote_missing"
            elif _duplicate(self.hass, remote):
                errors[CONF_REMOTE_ENTITY] = "already_configured"
            else:
                state = self.hass.states.get(remote)
                return self.async_create_entry(
                    title=f"Universal IR RF - {state.name}",
                    data={CONF_REMOTE_ENTITY: remote},
                )
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_REMOTE_ENTITY): _entity_selector()}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return UniversalRemoteOptionsFlow()


class UniversalRemoteOptionsFlow(config_entries.OptionsFlow):
    """Manage provider actions without reloading Home Assistant for each command."""

    def __init__(self) -> None:
        self._device = "device"
        self._command = "power"
        self._type = "ir"
        self._type_initialized = False
        self._alternative = False
        self._status = ""
        self._pending = False

    @property
    def _runtime(self) -> RemoteRuntime:
        return self.config_entry.runtime_data

    def _finish(self):
        # Avoid unnecessary config entry reload after learning/sending commands.
        return self.async_abort(reason="action_complete")

    def _set_status(self, en: str, vi: str) -> None:
        """Localize dynamic status text without rewriting translation files."""
        self._status = vi if self.hass.config.language == "vi" else en

    async def _codes(self):
        return await self._runtime.library.async_load()

    def _devices(self):
        return list(dict.fromkeys([
            self._device, *self._runtime.library.codes.keys(), *DEFAULT_DEVICES,
        ]))

    def _commands(self):
        commands = self._runtime.library.codes.get(self._device, {})
        return list(dict.fromkeys([self._command, *commands.keys(), *DEFAULT_COMMANDS]))

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            choice = user_input["menu_choice"]
            if choice == "learn_command":
                return await self.async_step_learn_command()
            if choice == "library":
                return await self.async_step_library()
            if choice == "send_command":
                return await self.async_step_send_command()
            if choice == "settings":
                return await self.async_step_settings()
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema({
                vol.Required("menu_choice", default="learn_command"):
                    _choice_selector(
                        ["learn_command", "library", "send_command", "settings"],
                        "menu_choice",
                    ),
            }),
            description_placeholders={"remote": self._runtime.remote_entity},
        )

    async def async_step_learn_command(self, user_input=None):
        if not self._type_initialized:
            self._type = "ir"
            self._type_initialized = True
        errors = {}
        try:
            await self._codes()
        except Exception:
            _LOGGER.exception("Unable to read the remote metadata library")
            errors["base"] = "library_failed"
        if user_input is not None and not errors:
            self._device = str(user_input["device"]).strip()
            self._command = str(user_input["command"]).strip()
            self._type = user_input["command_type"]
            self._alternative = bool(user_input.get("alternative", False))
            if not self._device or not self._command:
                errors["base"] = "invalid_name"
            else:
                try:
                    await async_learn(
                        self.hass, self._runtime, device=self._device,
                        command=self._command, command_type=self._type,
                        alternative=self._alternative,
                    )
                except Exception:
                    _LOGGER.exception("Remote learn failed: %s", self._runtime.remote_entity)
                    errors["base"] = "learn_failed"
                else:
                    self._pending = True
                    self._set_status(
                        "Learned by remote provider. Test, then save metadata.",
                        "Hub đã học mã. Hãy phát thử rồi xác nhận lưu thông tin lệnh.",
                    )
                    return await self.async_step_confirm_test()
        return self.async_show_form(
            step_id="learn_command", errors=errors,
            data_schema=vol.Schema({
                vol.Required("device", default=self._device): _name_selector(self._devices()),
                vol.Required("command", default=self._command): _name_selector(self._commands()),
                vol.Required("command_type", default=self._type):
                    _choice_selector(["ir", "rf", "rf_315", "rf_433"], "command_type"),
                vol.Optional("alternative", default=self._alternative):
                    selector.BooleanSelector(),
            }),
            description_placeholders={"remote": self._runtime.remote_entity},
        )

    async def async_step_confirm_test(self, user_input=None):
        if not self._pending:
            return await self.async_step_init()
        errors = {}
        if user_input is not None:
            action = user_input["action_choice"]
            if action == "test":
                try:
                    await async_send(
                        self.hass, self._runtime, device=self._device,
                        command=self._command, repeats=int(user_input.get("repeats", 1)),
                    )
                except Exception:
                    _LOGGER.exception("Test command failed")
                    errors["base"] = "send_failed"
                else:
                    self._set_status(
                        "Test sent. Check the appliance before saving.",
                        "Đã phát thử. Hãy kiểm tra thiết bị trước khi lưu.",
                    )
            elif action in ("confirm", "save_and_next"):
                try:
                    await self._runtime.library.async_record(
                        self._device, self._command, self._type,
                    )
                except Exception:
                    _LOGGER.exception("Unable to persist metadata")
                    errors["base"] = "library_failed"
                else:
                    self._pending = False
                    if action == "save_and_next":
                        if self._command.startswith("speed_"):
                            suffix = self._command.removeprefix("speed_")
                            if suffix.isdigit():
                                level = int(suffix) + 1
                                self._command = (
                                    f"speed_{level}" if level <= self._runtime.fan_speed_count
                                    else "turn_off"
                                )
                        return await self.async_step_learn_command()
                    return self._finish()
            elif action == "relearn":
                return await self.async_step_learn_command()
            elif action == "delete_abort":
                try:
                    await async_delete(
                        self.hass, self._runtime, device=self._device,
                        command=self._command,
                    )
                except Exception:
                    _LOGGER.exception("Provider did not delete learned command")
                    errors["base"] = "delete_failed"
                else:
                    self._pending = False
                    return await self.async_step_init()
        return self.async_show_form(
            step_id="confirm_test", errors=errors,
            data_schema=vol.Schema({
                vol.Required("action_choice", default="test"):
                    _choice_selector([
                        "test", "confirm", "save_and_next", "relearn", "delete_abort",
                    ], "action_choice"),
                vol.Optional("repeats", default=DEFAULT_REPEATS):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=1, max=5, step=1,
                    )),
            }),
            description_placeholders={
                "status_info": self._status, "device": self._device,
                "command": self._command, "wave_type": self._type,
            },
        )

    async def async_step_library(self, user_input=None):
        errors = {}
        try:
            codes = await self._codes()
        except Exception:
            _LOGGER.exception("Unable to load remote library")
            codes = {}
            errors["base"] = "library_failed"
        pairs = [
            (device, command) for device, cmds in sorted(codes.items())
            for command in sorted(cmds)
        ]
        # Bound selector cardinality; library itself remains complete on disk.
        visible = pairs[:300]
        keys = {str(i): pair for i, pair in enumerate(visible)}
        if user_input is not None and not errors:
            action = user_input["lib_action"]
            if action == "back_menu":
                return await self.async_step_init()
            if action == "close":
                return self._finish()
            if action == "add_new":
                return await self.async_step_learn_command()
            selected = keys.get(user_input.get("selected_item", ""))
            if selected is None:
                errors["base"] = "invalid_name"
            else:
                self._device, self._command = selected
                try:
                    if action == "test":
                        await async_send(
                            self.hass, self._runtime,
                            device=self._device, command=self._command,
                        )
                        self._set_status("Test command sent.", "Đã gửi lệnh thử.")
                    elif action == "relearn":
                        return await self.async_step_learn_command()
                    elif action == "delete":
                        await async_delete(
                            self.hass, self._runtime, device=self._device,
                            command=self._command, local_only=True,
                        )
                        self._set_status(
                            "Removed metadata only; provider code is unchanged.",
                            "Đã xóa metadata; mã trên Hub vẫn giữ nguyên.",
                        )
                    elif action == "delete_remote":
                        await async_delete(
                            self.hass, self._runtime, device=self._device,
                            command=self._command,
                        )
                        self._set_status(
                            "Removed provider code and local metadata.",
                            "Đã xóa mã trên Hub và metadata cục bộ.",
                        )
                except Exception:
                    _LOGGER.exception("Unable to run library action")
                    errors["base"] = "library_action_failed"
                else:
                    return await self.async_step_library()
        choices = ["add_new", "back_menu", "close"]
        if visible:
            choices = ["test", "relearn", "delete", "delete_remote", *choices]
        fields = {
            vol.Required("lib_action", default="test" if visible else "add_new"):
                _choice_selector(choices, "lib_action"),
        }
        if visible:
            fields = {
                vol.Required("selected_item", default="0"):
                    selector.SelectSelector(selector.SelectSelectorConfig(
                        options=[
                            {"value": str(i), "label": f"{dev} / {cmd}"}
                            for i, (dev, cmd) in enumerate(visible)
                        ], mode=selector.SelectSelectorMode.DROPDOWN,
                    )),
                **fields,
            }
        return self.async_show_form(
            step_id="library", errors=errors, data_schema=vol.Schema(fields),
            description_placeholders={
                "banner": self._status or (
                    "Thư viện tên lệnh của remote."
                    if self.hass.config.language == "vi"
                    else "Per-remote metadata library."
                ),
                "library_summary": (
                    (f"{len(codes)} thiết bị, {len(pairs)} lệnh"
                     + (" (chỉ hiển thị 300 lệnh đầu)" if len(pairs) > 300 else ""))
                    if self.hass.config.language == "vi"
                    else (f"{len(codes)} devices, {len(pairs)} commands"
                          + (" (showing first 300)" if len(pairs) > 300 else ""))
                ),
            },
        )

    async def async_step_send_command(self, user_input=None):
        errors = {}
        try:
            await self._codes()
        except Exception:
            _LOGGER.exception("Unable to load remote library")
            errors["base"] = "library_failed"
        if user_input is not None and not errors:
            self._device = str(user_input.get("device", "")).strip()
            self._command = str(user_input["command"]).strip()
            if not self._command:
                errors["base"] = "invalid_name"
            else:
                try:
                    await async_send(
                        self.hass, self._runtime,
                        device=self._device or None, command=self._command,
                        repeats=int(user_input.get("repeats", 1)),
                    )
                except Exception:
                    _LOGGER.exception("Remote send failed")
                    errors["base"] = "send_failed"
                else:
                    return self._finish()
        return self.async_show_form(
            step_id="send_command", errors=errors,
            data_schema=vol.Schema({
                vol.Optional("device", default=self._device): selector.TextSelector(),
                vol.Required("command", default=self._command): _name_selector(self._commands()),
                vol.Optional("repeats", default=DEFAULT_REPEATS):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=1, max=5, step=1,
                    )),
            }),
        )

    async def async_step_settings(self, user_input=None):
        runtime = self._runtime
        errors = {}
        if user_input is not None:
            remote = user_input[CONF_REMOTE_ENTITY]
            if self.hass.states.get(remote) is None:
                errors[CONF_REMOTE_ENTITY] = "remote_missing"
            elif _duplicate(self.hass, remote, self.config_entry.entry_id):
                errors[CONF_REMOTE_ENTITY] = "already_configured"
            else:
                user_input[CONF_FAN_DEVICE] = str(user_input[CONF_FAN_DEVICE]).strip()
                if not user_input[CONF_FAN_DEVICE]:
                    errors[CONF_FAN_DEVICE] = "invalid_name"
                else:
                    # Only settings update an entry; action flows must not trigger reload.
                    return self.async_create_entry(
                        title="", data={**dict(self.config_entry.options), **user_input},
                    )
        return self.async_show_form(
            step_id="settings", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_REMOTE_ENTITY, default=runtime.remote_entity):
                    _entity_selector(),
                vol.Required(CONF_ENABLE_FAN, default=runtime.enable_fan):
                    selector.BooleanSelector(),
                vol.Required(CONF_FAN_DEVICE, default=runtime.fan_device):
                    selector.TextSelector(),
                vol.Required(CONF_FAN_SPEED_COUNT, default=runtime.fan_speed_count):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=1, max=10, step=1, mode=selector.NumberSelectorMode.BOX,
                    )),
                vol.Optional(CONF_RF_FREQUENCY_ENTITY, default=runtime.rf_frequency_entity or ""):
                    selector.TextSelector(),
            }),
        )
