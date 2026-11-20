"""Tests for the entities a station gets, from the example file."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.weather import DOMAIN as WEATHER_DOMAIN
from homeassistant.components.weather import SERVICE_GET_FORECASTS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.weewx_current_json.const import EVENT_ALERT

from .conftest import URL


async def _refresh(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_weather(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    state = hass.states.get("weather.backyard_weather")
    assert state is not None
    assert state.state == "partlycloudy"
    assert state.attributes["temperature"] == 21.5
    assert state.attributes["humidity"] == 61
    assert state.attributes["pressure"] == 1015.2
    assert state.attributes["wind_bearing"] == 230
    assert state.attributes["cloud_coverage"] == 44
    assert state.attributes["uv_index"] == 3.1
    assert state.attributes["attribution"] == "Weather from Backyard Weather"


async def test_forecasts(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    response = await hass.services.async_call(
        WEATHER_DOMAIN, SERVICE_GET_FORECASTS,
        {"entity_id": "weather.backyard_weather", "type": "hourly"},
        blocking=True, return_response=True,
    )
    hourly = response["weather.backyard_weather"]["forecast"]
    assert len(hourly) == 2
    assert hourly[0]["datetime"] == "2025-10-23T15:00:00+00:00"
    assert hourly[0]["condition"] == "rainy"
    assert hourly[0]["temperature"] == 20.0
    assert hourly[0]["precipitation_probability"] == 20

    response = await hass.services.async_call(
        WEATHER_DOMAIN, SERVICE_GET_FORECASTS,
        {"entity_id": "weather.backyard_weather", "type": "twice_daily"},
        blocking=True, return_response=True,
    )
    periods = response["weather.backyard_weather"]["forecast"]
    assert [(p["is_daytime"], p["condition"]) for p in periods] == [(False, "lightning-rainy"), (True, "sunny")]


async def test_clear_night(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry,
                           document: dict[str, Any]) -> None:
    document["observations"]["code"] = 800
    document["time"] = document["almanac"]["sunset"] + 600
    aioclient_mock.get(URL, text=json.dumps(document))
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("weather.backyard_weather").state == "clear-night"


async def test_sensors(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    expected = {
        "sensor.backyard_weather_temperature": ("21.5", "°C"),
        "sensor.backyard_weather_humidity": ("61", "%"),
        "sensor.backyard_weather_atmospheric_pressure": ("1015.2", "hPa"),
        "sensor.backyard_weather_wind_direction": ("230", "°"),
        "sensor.backyard_weather_rain_in_the_last_hour": ("1.27", "mm"),
        "sensor.backyard_weather_air_quality_index": ("46", None),
        "sensor.backyard_weather_today_s_high": ("23.1", "°C"),
        "sensor.backyard_weather_rain_today": ("3.05", "mm"),
        "sensor.backyard_weather_temperature_trend": ("4.6", "°C"),
        "sensor.backyard_weather_pressure_trend": ("-1.2", "hPa"),
        "sensor.backyard_weather_storm_rain": ("3.05", "mm"),
        "sensor.backyard_weather_last_rain": ("2025-10-23T14:00:00+00:00", None),
        "sensor.backyard_weather_indoor_temperature": ("21.2", "°C"),
        "sensor.backyard_weather_greenhouse": ("24.1", "°C"),
        "sensor.backyard_weather_soil_moisture_1": ("18", "cb"),
        "sensor.backyard_weather_hardware_warnings": ("1", None),
        "sensor.backyard_weather_signal": ("97", "%"),
        "sensor.backyard_weather_console_battery_voltage": ("4.62", "V"),
        "sensor.backyard_weather_wind_speed": ("12.888", "km/h"),
    }
    for entity_id, (value, unit) in expected.items():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == value, entity_id
        assert state.attributes.get("unit_of_measurement") == unit, entity_id

    high = hass.states.get("sensor.backyard_weather_today_s_high")
    assert high.attributes["time"] == "2025-10-23T14:30:00+00:00"
    aqi = hass.states.get("sensor.backyard_weather_air_quality_index")
    assert aqi.attributes["aqi_category"] == "Good"
    assert hass.states.get("sensor.backyard_weather_hardware_warnings").attributes["warnings"] == [
        "Wind sensor battery low"
    ]
    # Readings the station doesn't have get no sensor.
    assert hass.states.get("sensor.backyard_weather_snow_depth") is None
    assert hass.states.get("sensor.backyard_weather_illuminance") is None


async def test_unique_ids(hass: HomeAssistant, entity_registry: er.EntityRegistry,
                          setup_integration: MockConfigEntry) -> None:
    entry_id = setup_integration.entry_id
    assert entity_registry.async_get("weather.backyard_weather").unique_id == entry_id
    assert entity_registry.async_get("sensor.backyard_weather_temperature").unique_id == f"{entry_id}_temperature"
    assert entity_registry.async_get("sensor.backyard_weather_greenhouse").unique_id == f"{entry_id}_sensor_extraTemp1"


async def test_binary_sensors(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    alerts = hass.states.get("binary_sensor.backyard_weather_weather_alerts")
    assert alerts.state == STATE_ON
    assert alerts.attributes["count"] == 1
    alert = alerts.attributes["alerts"][0]
    assert alert["event"] == "Heat Advisory"
    assert alert["ends"] == "2025-10-24T00:00:00+00:00"
    assert hass.states.get("binary_sensor.backyard_weather_wind_sensor_battery").state == STATE_ON
    assert hass.states.get("binary_sensor.backyard_weather_outdoor_sensor_battery").state == STATE_OFF


async def test_alert_events(hass: HomeAssistant, freezer: FrozenDateTimeFactory, aioclient_mock: AiohttpClientMocker,
                            setup_integration: MockConfigEntry, document: dict[str, Any]) -> None:
    events = async_capture_events(hass, EVENT_ALERT)
    await _refresh(hass, freezer)
    assert events == [], "Alerts active at startup aren't announced."

    document["forecast"]["alerts"].append(
        {"id": "urn:oid:2", "event": "Flood Watch", "headline": "Flood Watch until Friday"}
    )
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, text=json.dumps(document))
    await _refresh(hass, freezer)
    assert [e.data["event"] for e in events] == ["Flood Watch"]
    assert events[0].data["station"] == "Backyard Weather"
    assert hass.states.get("binary_sensor.backyard_weather_weather_alerts").attributes["count"] == 2

    await _refresh(hass, freezer)
    assert len(events) == 1, "Announced once."

    document["forecast"]["alerts"] = []
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, text=json.dumps(document))
    await _refresh(hass, freezer)
    assert hass.states.get("binary_sensor.backyard_weather_weather_alerts").state == STATE_OFF


async def test_new_readings_add_sensors(hass: HomeAssistant, freezer: FrozenDateTimeFactory,
                                        aioclient_mock: AiohttpClientMocker, setup_integration: MockConfigEntry,
                                        document: dict[str, Any]) -> None:
    document["observations"]["snowdepth"] = 30
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, text=json.dumps(document))
    await _refresh(hass, freezer)
    assert hass.states.get("sensor.backyard_weather_snow_depth").state == "30"


async def test_unavailable_when_fetch_fails(hass: HomeAssistant, freezer: FrozenDateTimeFactory,
                                            aioclient_mock: AiohttpClientMocker,
                                            setup_integration: MockConfigEntry) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=500)
    await _refresh(hass, freezer)
    assert hass.states.get("weather.backyard_weather").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.backyard_weather_temperature").state == STATE_UNAVAILABLE


async def test_setup_retries_when_fetch_fails(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                              config_entry: MockConfigEntry) -> None:
    aioclient_mock.get(URL, status=503)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert setup_integration.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts_location(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    from custom_components.weewx_current_json.diagnostics import async_get_config_entry_diagnostics

    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert diagnostics["entry"]["url"] == "**REDACTED**"
    assert diagnostics["document"]["station"]["latitude"] == "**REDACTED**"
    assert diagnostics["document"]["observations"]["temperature"] == 21.5
