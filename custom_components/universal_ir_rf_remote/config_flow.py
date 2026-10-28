"""UI config and per-remote command management for IR/RF remote providers."""

from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import selector

from . import RemoteRuntime, async_delete, async_learn, async_send, async_remove_virtual_device
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
                display = user_input.get("name", "").strip() or state.name
                return self.async_create_entry(
                    title=f"Universal IR RF - {display}",
                    data={CONF_REMOTE_ENTITY: remote},
                )
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_REMOTE_ENTITY): _entity_selector(),
                vol.Optional("name", default=""): selector.TextSelector(),
            }),
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
        self._learn_task: asyncio.Task | None = None
        self._learn_error: str | None = None
        self._device_id = ""
        self._fan_device_id = ""
        self._fan_mode = "add"
        self._fan_count = 6

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
            if choice == "devices":
                return await self.async_step_devices()
            if choice == "import_code":
                return await self.async_step_import_code()
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
                vol.Required("menu_choice", default="devices"):
                    _choice_selector(
                        ["devices", "import_code", "learn_command", "library", "send_command", "settings"],
                        "menu_choice",
                    ),
            }),
            description_placeholders={"remote": self._runtime.remote_entity},
        )

    async def async_step_devices(self, user_input=None):
        """Create and edit virtual appliances, not Home Assistant config entries."""
        errors = {}
        try:
            await self._codes()
        except Exception:
            _LOGGER.exception("Cannot load virtual appliances")
            errors["base"] = "library_failed"
        devices = self._runtime.library.devices
        if user_input is not None and not errors:
            action = user_input["device_action"]
            if action == "create":
                return await self.async_step_create_device()
            if action == "back_menu":
                return await self.async_step_init()
            selected = user_input.get("selected_device")
            if selected in devices:
                self._device_id = selected
                self._device = devices[selected]["name"]
                if action == "edit":
                    return await self.async_step_edit_device()
                if action == "commands":
                    return await self.async_step_manage_commands()
                if action == "learn":
                    return await self.async_step_learn_command()
                if action == "import_code":
                    return await self.async_step_import_code()
            errors["base"] = "invalid_name"
        choices = ["create", "back_menu"] if not devices else [
            "commands", "edit", "learn", "import_code", "create", "back_menu",
        ]
        fields = {vol.Required("device_action", default=choices[0]):
                  _choice_selector(choices, "device_action")}
        if devices:
            fields[vol.Required("selected_device", default=next(iter(devices)))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=[{"value": key, "label": dev["name"]}
                             for key, dev in devices.items()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ))
            )
        return self.async_show_form(
            step_id="devices", errors=errors, data_schema=vol.Schema(fields),
            description_placeholders={"device_count": str(len(devices))},
        )

    async def async_step_create_device(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                self._device_id = await self._runtime.library.async_create_device(
                    user_input["name"], kind=user_input["kind"],
                    provider_device=user_input.get("provider_device") or None,
                )
                self._device = user_input["name"].strip()
            except ValueError:
                errors["base"] = "invalid_name"
            except Exception:
                _LOGGER.exception("Create appliance failed")
                errors["base"] = "library_failed"
            else:
                return await self.async_step_devices()
        return self.async_show_form(step_id="create_device", errors=errors,
            data_schema=vol.Schema({
                vol.Required("name"): selector.TextSelector(),
                vol.Required("kind", default="generic"):
                    _choice_selector(["generic", "fan", "tv", "light"], "kind"),
                vol.Optional("provider_device"): selector.TextSelector(),
            }))

    async def async_step_edit_device(self, user_input=None):
        dev = self._runtime.library.devices.get(self._device_id)
        if not dev:
            return await self.async_step_devices()
        errors = {}
        if user_input is not None:
            if user_input["edit_action"] == "delete":
                return await self.async_step_confirm_delete_device()
            try:
                await self._runtime.library.async_update_device(
                    self._device_id, name=user_input["name"], kind=user_input["kind"],
                )
                self._device = user_input["name"].strip()
            except ValueError:
                errors["base"] = "invalid_name"
            except Exception:
                _LOGGER.exception("Edit appliance failed")
                errors["base"] = "library_failed"
            else:
                return await self.async_step_devices()
        return self.async_show_form(step_id="edit_device", errors=errors,
            data_schema=vol.Schema({
                vol.Required("name", default=dev["name"]): selector.TextSelector(),
                vol.Required("kind", default=dev.get("kind", "generic")):
                    _choice_selector(["generic", "fan", "tv", "light"], "kind"),
                vol.Required("edit_action", default="save"):
                    _choice_selector(["save", "delete"], "edit_action"),
            }), description_placeholders={"provider_device": dev["provider_device"]})

    async def async_step_confirm_delete_device(self, user_input=None):
        dev = self._runtime.library.devices.get(self._device_id)
        if not dev:
            return await self.async_step_devices()
        errors = {}
        if user_input is not None:
            if not user_input["confirm"]:
                return await self.async_step_devices()
            try:
                await async_remove_virtual_device(self.hass, self._runtime, self._device_id)
            except Exception:
                _LOGGER.exception("Delete appliance failed")
                errors["base"] = "library_failed"
            else:
                self._device_id = ""
                return await self.async_step_devices()
        return self.async_show_form(step_id="confirm_delete_device", errors=errors,
            data_schema=vol.Schema({vol.Required("confirm", default=False):
                                    selector.BooleanSelector()}),
            description_placeholders={"device": dev["name"],
                                      "command_count": str(len(dev["commands"]))})

    async def async_step_manage_commands(self, user_input=None):
        dev = self._runtime.library.devices.get(self._device_id)
        if not dev:
            return await self.async_step_devices()
        self._device = dev["name"]
        commands = dev["commands"]
        errors = {}
        if user_input is not None:
            action = user_input["command_action"]
            if action == "back":
                return await self.async_step_devices()
            if action == "import_code":
                return await self.async_step_import_code()
            if action == "learn":
                return await self.async_step_learn_command()
            command = user_input.get("selected_command")
            if command in commands:
                self._command = command
                if action == "edit":
                    return await self.async_step_edit_command()
                if action == "delete":
                    return await self.async_step_confirm_delete_command()
                try:
                    await async_send(self.hass, self._runtime,
                                     device=self._device, command=command)
                except Exception:
                    _LOGGER.exception("Send saved command failed")
                    errors["base"] = "send_failed"
                else:
                    self._set_status("Command sent.", "Da gui lenh.")
            else:
                errors["base"] = "invalid_name"
        choices = ["import_code", "learn", "back"] if not commands else [
            "test", "edit", "delete", "import_code", "learn", "back",
        ]
        fields = {vol.Required("command_action", default=choices[0]):
                  _choice_selector(choices, "command_action")}
        if commands:
            fields[vol.Required("selected_command", default=next(iter(commands)))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=list(commands), mode=selector.SelectSelectorMode.DROPDOWN,
                ))
            )
        return self.async_show_form(step_id="manage_commands", errors=errors,
            data_schema=vol.Schema(fields),
            description_placeholders={"device": dev["name"],
                                      "command_count": str(len(commands))})

    async def async_step_edit_command(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self._runtime.library.async_update_command(
                    self._device_id, self._command, name=user_input["name"],
                )
                self._command = user_input["name"].strip()
            except ValueError:
                errors["base"] = "invalid_name"
            except Exception:
                _LOGGER.exception("Rename command failed")
                errors["base"] = "library_failed"
            else:
                return await self.async_step_manage_commands()
        return self.async_show_form(step_id="edit_command", errors=errors,
            data_schema=vol.Schema({
                vol.Required("name", default=self._command): selector.TextSelector(),
            }), description_placeholders={"command": self._command})

    async def async_step_confirm_delete_command(self, user_input=None):
        errors = {}
        if user_input is not None:
            if not user_input["confirm"]:
                return await self.async_step_manage_commands()
            try:
                await self._runtime.library.async_remove(self._device_id, self._command)
            except Exception:
                _LOGGER.exception("Delete command failed")
                errors["base"] = "library_failed"
            else:
                return await self.async_step_manage_commands()
        return self.async_show_form(step_id="confirm_delete_command", errors=errors,
            data_schema=vol.Schema({vol.Required("confirm", default=False):
                                    selector.BooleanSelector()}),
            description_placeholders={"device": self._device, "command": self._command})

    async def async_step_import_code(self, user_input=None):
        errors = {}
        try:
            await self._codes()
        except Exception:
            _LOGGER.exception("Cannot load library for import")
            errors["base"] = "library_failed"
        if user_input is not None and not errors:
            self._device = str(user_input["device"]).strip()
            self._command = str(user_input["command"]).strip()
            try:
                await self._runtime.library.async_record(
                    self._device, self._command, user_input["command_type"],
                    raw_code=user_input["code"],
                )
            except ValueError:
                errors["base"] = "invalid_code"
            except Exception:
                _LOGGER.exception("Import code failed")
                errors["base"] = "library_failed"
            else:
                self._set_status("Saved raw code to local library.",
                                 "Da luu ma vao thu vien cuc bo.")
                return self._finish()
        return self.async_show_form(step_id="import_code", errors=errors,
            data_schema=vol.Schema({
                vol.Required("device", default=self._device): _name_selector(self._devices()),
                vol.Required("command", default=self._command): selector.TextSelector(),
                vol.Required("command_type", default="rf"):
                    _choice_selector(["ir", "rf"], "command_type"),
                vol.Required("code"):
                    selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            }), description_placeholders={"remote": self._runtime.remote_entity})

    async def async_step_learn_command(self, user_input=None):
        """Configure a one-click learning session using the provider's native API.

        Selecting Learn starts the service call in a task; HA renders a progress
        view immediately, instead of keeping an unresponsive Submit dialog open.
        Broadlink IR then needs one press. Broadlink RF still needs a frequency
        sweep followed by a second press; the provider controls those stages.
        """
        if not self._type_initialized:
            self._type = "ir"
            self._type_initialized = True
        errors = {}
        if self._learn_error:
            errors["base"] = self._learn_error
            self._learn_error = None
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
            elif self._learn_task is not None and not self._learn_task.done():
                return await self.async_step_learn_progress()
            else:
                remote_state = self.hass.states.get(self._runtime.remote_entity)
                if remote_state is None or remote_state.state in ("unknown", "unavailable"):
                    errors["base"] = "remote_unavailable"
                else:
                    self._pending = False
                    # Do not await here: the UI must show 'waiting for signal'
                    # while Broadlink receives data, not after it finishes.
                    self._learn_task = self.hass.async_create_task(
                        async_learn(
                            self.hass, self._runtime, device=self._device,
                            command=self._command, command_type=self._type,
                            alternative=self._alternative,
                        ),
                        f"{DOMAIN} learn {self._runtime.remote_entity}",
                    )
                    return await self.async_step_learn_progress()
        return self.async_show_form(
            step_id="learn_command", errors=errors,
            data_schema=vol.Schema({
                vol.Required("device", default=self._device): _name_selector(self._devices()),
                vol.Required("command", default=self._command): _name_selector(self._commands()),
                # The HA remote API accepts only IR or RF. Separate 315/433
                # choices are not supported by Broadlink's learn_command API.
                vol.Required("command_type", default=self._type):
                    _choice_selector(["ir", "rf"], "command_type"),
                vol.Optional("alternative", default=self._alternative):
                    selector.BooleanSelector(),
            }),
            description_placeholders={"remote": self._runtime.remote_entity},
        )

    async def async_step_learn_progress(self, user_input=None):
        """Display a live waiting screen until remote.learn_command finishes."""
        task = self._learn_task
        if task is None:
            return await self.async_step_learn_command()
        if not task.done():
            return self.async_show_progress(
                step_id="learn_progress",
                progress_action="waiting_rf" if self._type == "rf" else "waiting_ir",
                progress_task=task,
                description_placeholders={
                    "remote": self._runtime.remote_entity,
                    "device": self._device,
                    "command": self._command,
                },
            )
        return self.async_show_progress_done(next_step_id="learn_result")

    async def async_step_learn_result(self, user_input=None):
        """Only allow saving after a completed provider call and user test."""
        task = self._learn_task
        if task is None:
            return await self.async_step_learn_command()
        if not task.done():
            return await self.async_step_learn_progress()
        self._learn_task = None
        try:
            task.result()
        except asyncio.CancelledError:
            # Closing the progress dialog cancels the task; never save metadata.
            self._learn_error = "learn_cancelled"
        except (TimeoutError, asyncio.TimeoutError):
            _LOGGER.warning(
                "Timed out learning %s/%s on %s", self._device, self._command,
                self._runtime.remote_entity,
            )
            self._learn_error = "learn_timeout"
        except ServiceValidationError:
            _LOGGER.exception("Provider rejected learn request")
            self._learn_error = "learn_failed"
        except Exception:
            _LOGGER.exception("Remote learn failed on %s", self._runtime.remote_entity)
            self._learn_error = "learn_failed"
        if self._learn_error is not None:
            self._pending = False
            return await self.async_step_learn_command()
        self._pending = True
        self._set_status(
            "The provider's learning action has finished. Test the command on the physical appliance before saving: some providers report capture errors only in logs. If no signal is sent, try learning via Home Assistant's remote.learn_command action.",
            "Thao tác học của remote đã kết thúc. Hãy thử phát trên thiết bị thật trước khi lưu: một số bộ điều khiển chỉ báo lỗi thu tín hiệu trong log. Nếu chưa phát được, hãy thử action remote.learn_command trực tiếp trong Home Assistant.",
        )
        return await self.async_step_confirm_test()

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
        """Choose fan CRUD or provider settings without guessing a device name."""
        if user_input is not None:
            action = user_input["settings_action"]
            if action == "remote_settings":
                return await self.async_step_remote_settings()
            if action in ("fan_add", "fan_edit", "fan_rename", "fan_delete"):
                self._fan_mode = action.removeprefix("fan_")
                return await self.async_step_fan_pick()
            return await self.async_step_init()
        return self.async_show_form(step_id="settings", data_schema=vol.Schema({
            vol.Required("settings_action", default="fan_add"):
                _choice_selector(
                    ["fan_add", "fan_edit", "fan_rename", "fan_delete", "remote_settings", "back_menu"],
                    "settings_action",
                ),
        }))

    async def async_step_fan_pick(self, user_input=None):
        """Only show appliances belonging to this specific remote config entry."""
        errors = {}
        try:
            await self._codes()
        except Exception:
            _LOGGER.exception("Cannot load appliances for fan selection")
            errors["base"] = "library_failed"
        devices = self._runtime.library.devices
        candidates = {
            key: dev for key, dev in devices.items()
            if ((self._fan_mode == "add" and not dev.get("fan") and dev["commands"])
                or (self._fan_mode != "add" and dev.get("fan")))
        }
        if not candidates:
            errors["base"] = "no_fan_devices" if not errors else errors["base"]
        elif user_input is not None and not errors:
            selected = user_input["fan_device_id"]
            if selected not in candidates:
                errors["base"] = "invalid_name"
            else:
                self._fan_device_id = selected
                existing = candidates[selected].get("fan", {})
                self._fan_count = len(existing.get("speeds", [])) or min(
                    len(candidates[selected]["commands"]), 6
                )
                if self._fan_mode == "delete":
                    return await self.async_step_fan_confirm_delete()
                if self._fan_mode == "rename":
                    return await self.async_step_fan_rename()
                return await self.async_step_fan_count()
        fields = {}
        if candidates:
            fields[vol.Required("fan_device_id", default=next(iter(candidates)))] = (
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=[{"value": key, "label": dev["name"]}
                             for key, dev in candidates.items()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ))
            )
        return self.async_show_form(
            step_id="fan_pick", errors=errors, data_schema=vol.Schema(fields),
            description_placeholders={
                "remote": self._runtime.remote_entity,
                "action": self._fan_mode,
            },
        )

    async def async_step_fan_count(self, user_input=None):
        dev = self._runtime.library.devices.get(self._fan_device_id)
        if dev is None:
            return await self.async_step_fan_pick()
        if user_input is not None:
            self._fan_count = int(user_input["fan_speed_count"])
            if 1 <= self._fan_count <= min(10, len(dev["commands"])):
                return await self.async_step_fan_map()
        return self.async_show_form(
            step_id="fan_count",
            data_schema=vol.Schema({
                vol.Required("fan_speed_count", default=self._fan_count):
                    selector.NumberSelector(selector.NumberSelectorConfig(
                        min=1, max=min(10, len(dev["commands"])), step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )),
            }),
            description_placeholders={"device": dev["name"]},
        )

    async def async_step_fan_map(self, user_input=None):
        dev = self._runtime.library.devices.get(self._fan_device_id)
        if not dev:
            return await self.async_step_fan_pick()
        existing = dev.get("fan") or {}
        options = [
            {"value": cmd["id"], "label": label}
            for label, cmd in dev["commands"].items()
        ]
        ids = {item["value"] for item in options}
        errors = {}
        if user_input is not None:
            speeds = [user_input[f"speed_{i}"] for i in range(1, self._fan_count + 1)]
            off = user_input["off_command"]
            off = None if off == "__none__" else off
            if (any(s not in ids for s in speeds)
                    or len(set(speeds)) != len(speeds)
                    or (off is not None and (off not in ids or off in speeds))):
                errors["base"] = "invalid_fan_commands"
            else:
                try:
                    await self._runtime.library.async_configure_fan(
                        self._fan_device_id, speeds, off_id=off,
                    )
                except ValueError:
                    errors["base"] = "invalid_fan_commands"
                except Exception:
                    _LOGGER.exception("Failed to save fan mapping")
                    errors["base"] = "library_failed"
                else:
                    # The old fan was tied to the remote hub, not to a virtual
                    # appliance. Disable it on the first mapped fan migration.
                    if self._runtime.enable_fan:
                        return self.async_create_entry(
                            title="", data={**dict(self.config_entry.options),
                                            CONF_ENABLE_FAN: False},
                        )
                    return await self.async_step_settings()
        defaults = existing.get("speeds", [])
        fields = {}
        for i in range(1, self._fan_count + 1):
            preferred = defaults[i - 1] if i <= len(defaults) else options[i - 1]["value"]
            fields[vol.Required(f"speed_{i}", default=preferred)] = (
                selector.SelectSelector(selector.SelectSelectorConfig(
                    options=options, mode=selector.SelectSelectorMode.DROPDOWN,
                ))
            )
        # Preselect a dedicated, explicitly named OFF code on new mappings.
        # Save its stable ID so later renaming never changes the OFF action.
        auto_off = next((record["id"] for label, record in dev["commands"].items()
                         if label.strip().casefold() in ("turn_off", "off", "power_off")
                         and record.get("id") not in defaults), None)
        off_default = existing.get("off") or auto_off or "__none__"
        fields[vol.Required("off_command", default=off_default)] = (
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=[{"value": "__none__", "label": "No explicit OFF (auto-detect named OFF code)"}, *options],
                mode=selector.SelectSelectorMode.DROPDOWN,
            ))
        )
        return self.async_show_form(
            step_id="fan_map", errors=errors, data_schema=vol.Schema(fields),
            description_placeholders={"device": dev["name"],
                                      "remote": self._runtime.remote_entity},
        )

    async def async_step_fan_rename(self, user_input=None):
        """Rename the selected virtual appliance; fan command mappings remain stable."""
        dev = self._runtime.library.devices.get(self._fan_device_id)
        if not dev or not dev.get("fan"):
            return await self.async_step_settings()
        errors = {}
        if user_input is not None:
            try:
                await self._runtime.library.async_update_device(
                    self._fan_device_id, name=user_input["name"],
                )
            except ValueError:
                errors["base"] = "invalid_name"
            except Exception:
                _LOGGER.exception("Cannot rename virtual fan appliance")
                errors["base"] = "library_failed"
            else:
                return await self.async_step_settings()
        return self.async_show_form(
            step_id="fan_rename", errors=errors,
            data_schema=vol.Schema({
                vol.Required("name", default=dev["name"]): selector.TextSelector(),
            }),
            description_placeholders={"device": dev["name"]},
        )

    async def async_step_fan_confirm_delete(self, user_input=None):
        dev = self._runtime.library.devices.get(self._fan_device_id)
        if not dev or not dev.get("fan"):
            return await self.async_step_settings()
        errors = {}
        if user_input is not None:
            if not user_input["confirm"]:
                return await self.async_step_settings()
            try:
                await self._runtime.library.async_remove_fan(self._fan_device_id)
            except Exception:
                _LOGGER.exception("Unable to remove fan entity configuration")
                errors["base"] = "library_failed"
            else:
                return await self.async_step_settings()
        return self.async_show_form(
            step_id="fan_confirm_delete", errors=errors,
            data_schema=vol.Schema({vol.Required("confirm", default=False):
                                    selector.BooleanSelector()}),
            description_placeholders={"device": dev["name"]},
        )

    async def async_step_remote_settings(self, user_input=None):
        """Provider options, separate from individual appliance mappings."""
        runtime = self._runtime
        errors = {}
        if user_input is not None:
            remote = user_input[CONF_REMOTE_ENTITY]
            if self.hass.states.get(remote) is None:
                errors[CONF_REMOTE_ENTITY] = "remote_missing"
            elif _duplicate(self.hass, remote, self.config_entry.entry_id):
                errors[CONF_REMOTE_ENTITY] = "already_configured"
            else:
                updated = {**dict(self.config_entry.options), **user_input}
                updated[CONF_RF_FREQUENCY_ENTITY] = user_input.get(CONF_RF_FREQUENCY_ENTITY, "")
                return self.async_create_entry(title="", data=updated)
        fields = {
            vol.Required(CONF_REMOTE_ENTITY, default=runtime.remote_entity):
                _entity_selector(),
        }
        # Only advanced providers exposing an actual number.* band control need
        # this field. Broadlink RF automatically sweeps its hardware frequency.
        freq_key = (vol.Optional(CONF_RF_FREQUENCY_ENTITY,
                                 default=runtime.rf_frequency_entity)
                    if runtime.rf_frequency_entity else vol.Optional(CONF_RF_FREQUENCY_ENTITY))
        fields[freq_key] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="number")
        )
        if runtime.enable_fan:
            fields[vol.Required(CONF_ENABLE_FAN, default=True)] = selector.BooleanSelector()
        return self.async_show_form(step_id="remote_settings", errors=errors,
                                    data_schema=vol.Schema(fields))
