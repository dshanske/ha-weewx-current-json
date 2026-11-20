"""The station as a weather entity, with the NWS forecast when the station has weewx-nws."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.weather import (
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.sun import is_up

from . import api
from .coordinator import WeewxConfigEntry, WeewxCoordinator
from .entity import attribution, device_info

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeewxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the weather entity."""
    async_add_entities([WeewxWeather(entry.runtime_data)])


def _forecast(item: dict[str, Any], twice_daily: bool) -> Forecast | None:
    start = api.number(item, "time")
    if start is None:
        return None
    daytime = item.get("daytime") if isinstance(item.get("daytime"), bool) else None
    forecast = Forecast(
        datetime=datetime.fromtimestamp(start, UTC).isoformat(),
        condition=api.ha_condition(item.get("code"), daytime),
        native_temperature=api.number(item, "temperature"),
        native_dew_point=api.number(item, "dewpoint"),
        humidity=api.number(item, "humidity"),
        native_wind_speed=api.number(item, "windspeed"),
        wind_bearing=api.number(item, "winddegree"),
    )
    pop = api.number(item, "pop")
    if pop is not None:
        forecast["precipitation_probability"] = int(pop)
    if twice_daily:
        forecast["is_daytime"] = daytime
    return forecast


class WeewxWeather(SingleCoordinatorWeatherEntity[WeewxCoordinator]):
    """The station's current conditions, and its NWS forecast."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS

    def __init__(self, coordinator: WeewxCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.config_entry.entry_id
        self._attr_device_info = device_info(coordinator)
        self._attr_attribution = attribution(coordinator)

    @property
    def _observations(self) -> dict[str, Any]:
        return api.section(self.coordinator.data, "observations")

    def _value(self, key: str) -> float | None:
        return api.number(self._observations, key)

    @property
    def supported_features(self) -> WeatherEntityFeature:
        forecast = api.section(self.coordinator.data, "forecast")
        features = WeatherEntityFeature(0)
        if forecast.get("hourly"):
            features |= WeatherEntityFeature.FORECAST_HOURLY
        if forecast.get("periods"):
            features |= WeatherEntityFeature.FORECAST_TWICE_DAILY
        return features

    @property
    def condition(self) -> str | None:
        daytime = api.is_daytime(self.coordinator.data)
        if daytime is None:
            daytime = is_up(self.hass)
        return api.ha_condition(self._observations.get("code"), daytime)

    @property
    def native_temperature(self) -> float | None:
        return self._value("temperature")

    @property
    def native_apparent_temperature(self) -> float | None:
        return self._value("apptemp")

    @property
    def native_dew_point(self) -> float | None:
        return self._value("dewpoint")

    @property
    def humidity(self) -> float | None:
        return self._value("humidity")

    @property
    def native_pressure(self) -> float | None:
        return self._value("pressure")

    @property
    def native_wind_speed(self) -> float | None:
        return self._value("windspeed")

    @property
    def native_wind_gust_speed(self) -> float | None:
        return self._value("windgust")

    @property
    def wind_bearing(self) -> float | None:
        return self._value("winddegree")

    @property
    def cloud_coverage(self) -> int | None:
        value = self._value("cloudiness")
        return None if value is None else int(value)

    @property
    def uv_index(self) -> float | None:
        return self._value("uv")

    def _forecasts(self, key: str, twice_daily: bool) -> list[Forecast] | None:
        items = api.section(self.coordinator.data, "forecast").get(key)
        if not isinstance(items, list):
            return None
        forecasts = [_forecast(item, twice_daily) for item in items if isinstance(item, dict)]
        return [f for f in forecasts if f is not None] or None

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        return self._forecasts("hourly", twice_daily=False)

    @callback
    def _async_forecast_twice_daily(self) -> list[Forecast] | None:
        return self._forecasts("periods", twice_daily=True)
