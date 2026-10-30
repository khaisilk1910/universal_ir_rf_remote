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


# UI grouping only: selecting a type does not create a native HA climate/cover/light entity.
# Values are stable IDs stored in the per-remote library; do not rename or reorder old IDs.
APPLIANCE_KINDS: tuple[str, ...] = (
    'generic',
    'air_conditioner',
    'air_cooler',
    'air_purifier',
    'heater',
    'fireplace',
    'fan',
    'ceiling_fan',
    'exhaust_fan',
    'humidifier',
    'dehumidifier',
    'water_heater',
    'tv',
    'projector',
    'projector_screen',
    'set_top_box',
    'streaming_box',
    'satellite_receiver',
    'av_receiver',
    'amplifier',
    'soundbar',
    'speaker',
    'dvd_player',
    'media_player',
    'light',
    'led_strip',
    'dimmer',
    'switch',
    'smart_plug',
    'curtain',
    'blinds',
    'roller_shutter',
    'awning',
    'garage_door',
    'gate',
    'door_lock',
    'doorbell',
    'alarm',
    'camera',
    'robot_vacuum',
    'irrigation',
    'motorized_bed',
)
FAN_APPLIANCE_KINDS = frozenset(("fan", "ceiling_fan", "exhaust_fan"))
