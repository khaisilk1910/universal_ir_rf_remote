"""Diagnostics with no learned waveforms or other-provider private data."""

from homeassistant.core import HomeAssistant

from . import ManagerConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ManagerConfigEntry,
) -> dict:
    runtime = entry.runtime_data
    return {
        "config_entry_id": entry.entry_id,
        "remote_entity": runtime.remote_entity,
        "fan_enabled": runtime.enable_fan,
        "fan_device": runtime.fan_device if runtime.enable_fan else None,
        "fan_speed_count": runtime.fan_speed_count if runtime.enable_fan else None,
        "rf_frequency_entity": runtime.rf_frequency_entity,
        "library_loaded": runtime.library.loaded,
        "library_filename": runtime.library.path.name,
        "total_devices": len(runtime.library.codes) if runtime.library.loaded else None,
        "total_commands": runtime.library.command_count,
    }
