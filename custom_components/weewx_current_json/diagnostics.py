"""Diagnostics: the station's latest file, without its location."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

from .coordinator import WeewxConfigEntry

TO_REDACT = {CONF_URL, "latitude", "longitude", "altitude", "url", "webcam"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: WeewxConfigEntry) -> dict[str, Any]:
    """Return the config entry and the latest file, with addresses and coordinates removed."""
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "document": async_redact_data(entry.runtime_data.data, TO_REDACT),
    }
