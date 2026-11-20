"""Constants for the WeeWX Current Conditions integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "weewx_current_json"

CONF_SCAN_INTERVAL: Final = "scan_interval"
# Minutes. WeeWX writes the file every archive interval, five minutes by default.
DEFAULT_SCAN_INTERVAL: Final = 5
MIN_SCAN_INTERVAL: Final = 1
MAX_SCAN_INTERVAL: Final = 60

# Fired once for each NWS alert that appears in the file after Home Assistant started.
EVENT_ALERT: Final = f"{DOMAIN}_alert"

DEFAULT_ATTRIBUTION: Final = "Data from a WeeWX weather station"
