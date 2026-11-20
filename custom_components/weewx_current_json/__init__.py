"""The WeeWX Current Conditions integration.

Reads the current.json file that the weewx-current-json extension writes beside a WeeWX
station's web pages, and turns it into a weather entity, sensors and an NWS alerts sensor.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import WeewxConfigEntry, WeewxCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.WEATHER]


async def async_setup_entry(hass: HomeAssistant, entry: WeewxConfigEntry) -> bool:
    """Set up a station from a config entry."""
    coordinator = WeewxCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WeewxConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: WeewxConfigEntry) -> None:
    """Reload when the options change, to apply a new update interval."""
    await hass.config_entries.async_reload(entry.entry_id)
