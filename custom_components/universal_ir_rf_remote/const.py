"""Constants for Universal IR RF Remote Manager."""

DOMAIN = "universal_ir_rf_remote"
LIBRARY_FILE = "universal_ir_rf_remote_library.json"
SIGNAL_LIBRARY_UPDATED = f"{DOMAIN}_library_updated"
# A lightweight, per-config-entry notification after a successfully sent stored command.
SIGNAL_COMMAND_SENT = f"{DOMAIN}_command_sent"

CONF_REMOTE_ENTITY = "remote_entity"
CONF_FAN_DEVICE = "fan_device"
CONF_FAN_SPEED_COUNT = "fan_speed_count"
CONF_ENABLE_FAN = "enable_fan"
CONF_RF_FREQUENCY_ENTITY = "rf_frequency_entity"
CONF_ENTRY_ID = "config_entry_id"

DEFAULT_FAN_DEVICE = "fan"
DEFAULT_FAN_SPEED_COUNT = 6
DEFAULT_REPEATS = 1

DEFAULT_DEVICES = ("device",)
DEFAULT_COMMANDS = (
    "power", "on", "off", "toggle", "vol_up", "vol_down", "mute",
    "up", "down", "stop", "open", "close", "light", "reverse",
    "speed_1", "speed_2", "speed_3", "speed_4", "speed_5", "speed_6",
    "turn_off",
)
