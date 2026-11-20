"""Fetch the station's file on a schedule."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import api
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, EVENT_ALERT

_LOGGER = logging.getLogger(__name__)

type WeewxConfigEntry = ConfigEntry[WeewxCoordinator]


class WeewxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the latest copy of the station's file."""

    config_entry: WeewxConfigEntry

    def __init__(self, hass: HomeAssistant, entry: WeewxConfigEntry) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.url: str = entry.data[CONF_URL]
        # Alert ids already seen; None until the first fetch, so alerts already active when Home
        # Assistant starts don't fire events.
        self._seen_alerts: set[str] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            document = await api.fetch(async_get_clientsession(self.hass), self.url)
        except api.WeewxError as err:
            raise UpdateFailed(str(err)) from err
        self._announce_alerts(document)
        return document

    def _announce_alerts(self, document: dict[str, Any]) -> None:
        """Fire an event for each alert that wasn't in the file before."""
        alerts = [
            alert
            for alert in api.section(document, "forecast").get("alerts") or []
            if isinstance(alert, dict)
        ]
        ids = {str(alert.get("id") or alert.get("headline") or alert.get("event")) for alert in alerts}
        if self._seen_alerts is not None:
            station = api.section(document, "station")
            for alert in alerts:
                key = str(alert.get("id") or alert.get("headline") or alert.get("event"))
                if key not in self._seen_alerts:
                    self.hass.bus.async_fire(
                        EVENT_ALERT,
                        {
                            "config_entry_id": self.config_entry.entry_id,
                            "station": station.get("name") or station.get("id"),
                            **alert,
                        },
                    )
        self._seen_alerts = ids
