"""NWS alerts, and low batteries, as binary sensors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import api
from .coordinator import WeewxConfigEntry, WeewxCoordinator
from .entity import WeewxEntity

PARALLEL_UPDATES = 0

# Each alert's keys, as the extension writes them, in the order they're shown.
ALERT_KEYS = (
    "event", "headline", "severity", "urgency", "certainty", "area", "sender",
    "description", "instruction", "id",
)
ALERT_TIMES = ("issued", "onset", "ends", "expires")

# Names of WeeWX's battery fields, as weewx-current-json gives them in its warnings.
BATTERY_NAMES = {
    "outTempBatteryStatus": "Outdoor sensor battery",
    "inTempBatteryStatus": "Indoor sensor battery",
    "windBatteryStatus": "Wind sensor battery",
    "rainBatteryStatus": "Rain gauge battery",
    "txBatteryStatus": "Transmitter battery",
    "uvBatteryStatus": "UV sensor battery",
    "hailBatteryStatus": "Hail sensor battery",
    "snowBatteryStatus": "Snow sensor battery",
    **{f"batteryStatus{n}": f"Sensor {n} battery" for n in range(1, 9)},
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeewxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the alerts sensor, with weewx-nws, and a battery sensor for each battery."""
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def add_new() -> None:
        document = coordinator.data
        entities: list[BinarySensorEntity] = []
        if "forecast" in document and "alerts" not in added:
            added.add("alerts")
            entities.append(WeewxAlerts(coordinator))
        for field in sorted(api.section(document, "health").get("batteries") or {}):
            if f"battery_{field}" not in added:
                added.add(f"battery_{field}")
                entities.append(WeewxBattery(coordinator, field))
        if entities:
            async_add_entities(entities)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


def _alerts(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [a for a in api.section(document, "forecast").get("alerts") or [] if isinstance(a, dict)]


def _alert_attributes(alert: dict[str, Any]) -> dict[str, Any]:
    attributes = {key: alert[key] for key in ALERT_KEYS if alert.get(key)}
    for key in ALERT_TIMES:
        stamp = api.number(alert, key)
        if stamp is not None:
            attributes[key] = datetime.fromtimestamp(stamp, UTC).isoformat()
    return attributes


class WeewxAlerts(WeewxEntity, BinarySensorEntity):
    """On while NWS has an alert for the station, from weewx-nws."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_translation_key = "alerts"

    def __init__(self, coordinator: WeewxCoordinator) -> None:
        super().__init__(coordinator, "alerts")

    @property
    def is_on(self) -> bool:
        return bool(_alerts(self.coordinator.data))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        alerts = [_alert_attributes(alert) for alert in _alerts(self.coordinator.data)]
        return {"count": len(alerts), "alerts": alerts}


class WeewxBattery(WeewxEntity, BinarySensorEntity):
    """On when the extension warns that a battery is low."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WeewxCoordinator, field: str) -> None:
        super().__init__(coordinator, f"battery_{field}")
        self._field = field
        self._attr_name = BATTERY_NAMES.get(field, field)

    @property
    def available(self) -> bool:
        batteries = api.section(self.coordinator.data, "health").get("batteries") or {}
        return super().available and self._field in batteries

    @property
    def is_on(self) -> bool:
        # The extension knows each driver's way of reporting a low battery; trust its warnings.
        warnings = api.section(self.coordinator.data, "health").get("warnings") or []
        return any(isinstance(w, dict) and w.get("field") == self._field for w in warnings)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        batteries = api.section(self.coordinator.data, "health").get("batteries") or {}
        return {"field": self._field, "status": batteries.get(self._field)}
