"""Sensors for the station's readings, today's extremes, the trend, rain and health."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    DEGREE,
    LIGHT_LUX,
    PERCENTAGE,
    UV_INDEX,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import api
from .coordinator import WeewxConfigEntry, WeewxCoordinator
from .entity import WeewxEntity

PARALLEL_UPDATES = 0

MEASUREMENT = SensorStateClass.MEASUREMENT
DEGREE_DAYS = "°C·d"


@dataclass(frozen=True, kw_only=True)
class WeewxSensorDescription(SensorEntityDescription):
    """A sensor read from a key of a section of the file."""

    section: str = "observations"
    # The key in the section; the description's own key when None.
    field: str | None = None
    # A key of the same section holding the time the value was reached, as a state attribute.
    time_field: str | None = None
    value_fn: Callable[[dict[str, Any]], Any] | None = None
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _temperature(key: str, **kwargs: Any) -> WeewxSensorDescription:
    kwargs.setdefault("state_class", MEASUREMENT)
    kwargs.setdefault("translation_key", key)
    return WeewxSensorDescription(
        key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        **kwargs,
    )


def _precipitation(key: str, **kwargs: Any) -> WeewxSensorDescription:
    kwargs.setdefault("state_class", MEASUREMENT)
    kwargs.setdefault("translation_key", key)
    return WeewxSensorDescription(
        key=key,
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        suggested_display_precision=1,
        **kwargs,
    )


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value, UTC)


def _iso(value: Any) -> str | None:
    """A time from the file as an ISO 8601 string, for a state attribute."""
    stamp = _timestamp(value)
    return None if stamp is None else stamp.isoformat()


def _aqi_attributes(observations: dict[str, Any]) -> dict[str, Any]:
    return {key: observations[key] for key in ("aqi_category", "aqi_color") if observations.get(key)}


def _health_warnings(health: dict[str, Any]) -> int:
    return len([w for w in health.get("warnings") or [] if isinstance(w, dict)])


def _health_attributes(health: dict[str, Any]) -> dict[str, Any]:
    return {"warnings": [w.get("message") for w in health.get("warnings") or [] if isinstance(w, dict)]}


OBSERVATIONS: tuple[WeewxSensorDescription, ...] = (
    _temperature("temperature"),
    WeewxSensorDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=MEASUREMENT,
    ),
    _temperature("dewpoint"),
    _temperature("heatindex"),
    _temperature("windchill"),
    _temperature("apptemp"),
    WeewxSensorDescription(
        key="cloudbase",
        translation_key="cloudbase",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=MEASUREMENT,
        suggested_display_precision=0,
    ),
    WeewxSensorDescription(
        key="pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
    ),
    WeewxSensorDescription(
        key="windspeed",
        translation_key="windspeed",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
    ),
    WeewxSensorDescription(
        key="windgust",
        translation_key="windgust",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
    ),
    WeewxSensorDescription(
        key="winddegree",
        translation_key="winddegree",
        device_class=SensorDeviceClass.WIND_DIRECTION,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
        suggested_display_precision=0,
    ),
    _precipitation("rain", translation_key="rain_last_hour"),
    WeewxSensorDescription(
        key="rainrate",
        translation_key="rainrate",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
    ),
    _precipitation("snow", translation_key="snow_last_hour"),
    WeewxSensorDescription(
        key="snowrate",
        translation_key="snowrate",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
    ),
    WeewxSensorDescription(
        key="snowdepth",
        translation_key="snowdepth",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        state_class=MEASUREMENT,
        suggested_display_precision=0,
    ),
    WeewxSensorDescription(
        key="radiation",
        translation_key="radiation",
        device_class=SensorDeviceClass.IRRADIANCE,
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        state_class=MEASUREMENT,
        suggested_display_precision=0,
    ),
    WeewxSensorDescription(
        key="illuminance",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=LIGHT_LUX,
        state_class=MEASUREMENT,
        suggested_display_precision=0,
    ),
    WeewxSensorDescription(
        key="uv",
        translation_key="uv",
        native_unit_of_measurement=UV_INDEX,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
    ),
    WeewxSensorDescription(
        key="cloudiness",
        translation_key="cloudiness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=MEASUREMENT,
        suggested_display_precision=0,
    ),
    WeewxSensorDescription(
        key="pm1_0",
        device_class=SensorDeviceClass.PM1,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=MEASUREMENT,
    ),
    WeewxSensorDescription(
        key="pm2_5",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=MEASUREMENT,
    ),
    WeewxSensorDescription(
        key="pm10_0",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=MEASUREMENT,
    ),
    # Gases are in parts per million, WeeWX's METRICWX unit for them.
    WeewxSensorDescription(
        key="co",
        device_class=SensorDeviceClass.CO,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=MEASUREMENT,
    ),
    WeewxSensorDescription(
        key="co2",
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=MEASUREMENT,
    ),
    WeewxSensorDescription(
        key="o3",
        device_class=SensorDeviceClass.OZONE,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=MEASUREMENT,
    ),
    # Home Assistant's sulphur dioxide class has no ppm, so these have no device class.
    WeewxSensorDescription(
        key="so2",
        translation_key="so2",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=MEASUREMENT,
    ),
    WeewxSensorDescription(
        key="nh3",
        translation_key="nh3",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=MEASUREMENT,
    ),
    WeewxSensorDescription(
        key="pb",
        translation_key="pb",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=MEASUREMENT,
    ),
    WeewxSensorDescription(key="voc_index", translation_key="voc_index", state_class=MEASUREMENT),
    WeewxSensorDescription(key="nox_index", translation_key="nox_index", state_class=MEASUREMENT),
    WeewxSensorDescription(
        key="aqi",
        device_class=SensorDeviceClass.AQI,
        state_class=MEASUREMENT,
        attributes_fn=_aqi_attributes,
    ),
    WeewxSensorDescription(
        key="lightning_strikes",
        translation_key="lightning_strikes",
        state_class=MEASUREMENT,
    ),
    WeewxSensorDescription(
        key="lightning_distance",
        translation_key="lightning_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=MEASUREMENT,
        suggested_display_precision=0,
    ),
)

TODAY: tuple[WeewxSensorDescription, ...] = (
    _temperature("today_temperature_max", section="today", field="temperature_max",
                 time_field="temperature_max_time", state_class=None),
    _temperature("today_temperature_min", section="today", field="temperature_min",
                 time_field="temperature_min_time", state_class=None),
    WeewxSensorDescription(
        key="today_windgust_max",
        translation_key="today_windgust_max",
        section="today",
        field="windgust_max",
        time_field="windgust_max_time",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        suggested_display_precision=1,
    ),
    # Daily totals start again at midnight, which TOTAL_INCREASING takes as a reset.
    _precipitation("today_rain", section="today", field="rain", state_class=SensorStateClass.TOTAL_INCREASING),
    _precipitation("today_snow", section="today", field="snow", state_class=SensorStateClass.TOTAL_INCREASING),
    _precipitation("today_et", section="today", field="et", state_class=SensorStateClass.TOTAL_INCREASING),
    WeewxSensorDescription(
        key="today_windrun",
        translation_key="today_windrun",
        section="today",
        field="windrun",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    WeewxSensorDescription(
        key="today_lightning_strikes",
        translation_key="today_lightning_strikes",
        section="today",
        field="lightning_strikes",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    WeewxSensorDescription(
        key="today_heatdeg", translation_key="today_heatdeg", section="today", field="heatdeg",
        native_unit_of_measurement=DEGREE_DAYS, suggested_display_precision=1,
    ),
    WeewxSensorDescription(
        key="today_cooldeg", translation_key="today_cooldeg", section="today", field="cooldeg",
        native_unit_of_measurement=DEGREE_DAYS, suggested_display_precision=1,
    ),
    WeewxSensorDescription(
        key="today_growdeg", translation_key="today_growdeg", section="today", field="growdeg",
        native_unit_of_measurement=DEGREE_DAYS, suggested_display_precision=1,
    ),
)

OTHERS: tuple[WeewxSensorDescription, ...] = (
    # A change of temperature can't take a temperature device class: converting it to °F would
    # add 32. It stays in °C.
    WeewxSensorDescription(
        key="trend_temperature",
        translation_key="trend_temperature",
        section="trend",
        field="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
        attributes_fn=lambda trend: {"hours": trend.get("hours")},
    ),
    WeewxSensorDescription(
        key="trend_pressure",
        translation_key="trend_pressure",
        section="trend",
        field="pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
        attributes_fn=lambda trend: {"hours": trend.get("hours")},
    ),
    _precipitation("rain_last_24h", section="rain", field="last_24h"),
    _precipitation(
        "rain_storm",
        section="rain",
        field="storm",
        state_class=None,
        attributes_fn=lambda rain: {"start": _iso(rain.get("storm_start"))},
    ),
    WeewxSensorDescription(
        key="rain_last",
        translation_key="rain_last",
        section="rain",
        field="last",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda rain: _timestamp(rain.get("last")),
    ),
    _temperature("indoor_temperature", section="indoor", field="temperature"),
    WeewxSensorDescription(
        key="indoor_humidity",
        translation_key="indoor_humidity",
        section="indoor",
        field="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=MEASUREMENT,
    ),
    _temperature("indoor_dewpoint", section="indoor", field="dewpoint"),
    WeewxSensorDescription(
        key="health_warnings",
        translation_key="health_warnings",
        section="health",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_health_warnings,
        attributes_fn=_health_attributes,
    ),
    WeewxSensorDescription(
        key="signal",
        translation_key="signal",
        section="health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda health: api.number(health.get("signal"), "rxCheckPercent"),
    ),
)

DESCRIPTIONS = OBSERVATIONS + TODAY + OTHERS

# Extra sensors: (device class, unit, display precision) by the file's kind.
SENSOR_KINDS: dict[str, tuple[SensorDeviceClass | None, str | None, int]] = {
    "temperature": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 1),
    "soil_temperature": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 1),
    "leaf_temperature": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 1),
    "humidity": (SensorDeviceClass.HUMIDITY, PERCENTAGE, 0),
    "soil_moisture": (None, "cb", 0),
    "leaf_wetness": (None, None, 0),
}


def _value(description: WeewxSensorDescription, document: dict[str, Any]) -> Any:
    section = api.section(document, description.section)
    if description.value_fn is not None:
        return description.value_fn(section)
    return api.number(section, description.field or description.key)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeewxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a sensor for each reading the station has, adding more as they appear."""
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def add_new() -> None:
        document = coordinator.data
        entities: list[SensorEntity] = []
        for description in DESCRIPTIONS:
            if description.key not in added and _value(description, document) is not None:
                added.add(description.key)
                entities.append(WeewxSensor(coordinator, description))
        for item in document.get("sensors") or []:
            if isinstance(item, dict) and isinstance(item.get("field"), str):
                key = f"sensor_{item['field']}"
                if key not in added:
                    added.add(key)
                    entities.append(WeewxExtraSensor(coordinator, item))
        for field in sorted(api.section(document, "health").get("voltages") or {}):
            key = f"voltage_{field}"
            if key not in added:
                added.add(key)
                entities.append(WeewxVoltageSensor(coordinator, field))
        if entities:
            async_add_entities(entities)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class WeewxSensor(WeewxEntity, SensorEntity):
    """A reading from the file."""

    entity_description: WeewxSensorDescription

    def __init__(self, coordinator: WeewxCoordinator, description: WeewxSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return _value(self.entity_description, self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        description = self.entity_description
        section = api.section(self.coordinator.data, description.section)
        attributes: dict[str, Any] = {}
        if description.time_field:
            attributes["time"] = _iso(section.get(description.time_field))
        if description.attributes_fn is not None:
            attributes.update(description.attributes_fn(section))
        return attributes or None


class WeewxExtraSensor(WeewxEntity, SensorEntity):
    """One of the station's extra sensors, such as a soil probe, named in the file."""

    _attr_state_class = MEASUREMENT

    def __init__(self, coordinator: WeewxCoordinator, item: dict[str, Any]) -> None:
        super().__init__(coordinator, f"sensor_{item['field']}")
        self._field = item["field"]
        self._attr_name = str(item.get("name") or self._field)
        device_class, unit, precision = SENSOR_KINDS.get(str(item.get("kind")), (None, None, 1))
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_suggested_display_precision = precision

    def _item(self) -> dict[str, Any] | None:
        for item in self.coordinator.data.get("sensors") or []:
            if isinstance(item, dict) and item.get("field") == self._field:
                return item
        return None

    @property
    def native_value(self) -> float | None:
        return api.number(self._item(), "value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"field": self._field}


VOLTAGE_NAMES = {
    "consBatteryVoltage": "Console battery voltage",
    "supplyVoltage": "Supply voltage",
    "referenceVoltage": "Reference voltage",
    "heatingVoltage": "Heating voltage",
}


class WeewxVoltageSensor(WeewxEntity, SensorEntity):
    """A battery or supply voltage the hardware reports."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: WeewxCoordinator, field: str) -> None:
        super().__init__(coordinator, f"voltage_{field}")
        self._field = field
        self._attr_name = VOLTAGE_NAMES.get(field, field)

    @property
    def native_value(self) -> float | None:
        return api.number(api.section(self.coordinator.data, "health").get("voltages"), self._field)
