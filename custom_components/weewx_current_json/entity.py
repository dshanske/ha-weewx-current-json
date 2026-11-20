"""The base entity: one device per station."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api
from .const import DEFAULT_ATTRIBUTION, DOMAIN
from .coordinator import WeewxCoordinator


def device_info(coordinator: WeewxCoordinator) -> DeviceInfo:
    """Return the station's device."""
    document = coordinator.data
    station = api.section(document, "station")
    info = DeviceInfo(
        identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        name=str(station.get("name") or station.get("id") or "WeeWX"),
        manufacturer="WeeWX",
        model="weewx-current-json",
        entry_type=DeviceEntryType.SERVICE,
    )
    version = api.generator_version(document)
    if version:
        info["sw_version"] = version
    url = station.get("url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        info["configuration_url"] = url
    return info


def attribution(coordinator: WeewxCoordinator) -> str:
    """Return the station's attribution text, or a default."""
    station_attribution = api.section(coordinator.data, "station").get("attribution")
    if isinstance(station_attribution, dict) and station_attribution.get("text"):
        return str(station_attribution["text"])
    return DEFAULT_ATTRIBUTION


class WeewxEntity(CoordinatorEntity[WeewxCoordinator]):
    """An entity of a station."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WeewxCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = device_info(coordinator)
        self._attr_attribution = attribution(coordinator)
