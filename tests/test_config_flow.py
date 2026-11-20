"""Tests for setting up a station from the UI."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.weewx_current_json.const import CONF_SCAN_INTERVAL, DOMAIN

from .conftest import URL


async def test_user_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, document: dict[str, Any]) -> None:
    aioclient_mock.get(URL, text=json.dumps(document))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: "weather.example.com"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Backyard Weather"
    assert result["data"] == {CONF_URL: URL}
    assert result["result"].unique_id == URL


async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                        document: dict[str, Any]) -> None:
    aioclient_mock.get(URL, status=404)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # It recovers once the file is there.
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, text=json.dumps(document))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_not_a_station(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(URL, text="<html>Not here</html>")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL})
    assert result["errors"] == {"base": "invalid_format"}


async def test_user_flow_wrong_version(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                       document: dict[str, Any]) -> None:
    aioclient_mock.get(URL, text=json.dumps(dict(document, version=2)))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL})
    assert result["errors"] == {"base": "invalid_format"}


async def test_user_flow_already_configured(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                            config_entry: MockConfigEntry, document: dict[str, Any]) -> None:
    aioclient_mock.get(URL, text=json.dumps(document))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: "Weather.Example.com"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                           setup_integration: MockConfigEntry, document: dict[str, Any]) -> None:
    new_url = "https://wx.example.org/current.json"
    aioclient_mock.get(new_url, text=json.dumps(document))
    result = await setup_integration.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: "wx.example.org"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert setup_integration.data == {CONF_URL: new_url}
    assert setup_integration.unique_id == new_url


async def test_reconfigure_to_another_station(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker,
                                              setup_integration: MockConfigEntry, document: dict[str, Any]) -> None:
    other_url = "https://other.example.com/current.json"
    MockConfigEntry(domain=DOMAIN, unique_id=other_url, data={CONF_URL: other_url}).add_to_hass(hass)
    aioclient_mock.get(other_url, text=json.dumps(document))
    result = await setup_integration.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: other_url})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert setup_integration.data == {CONF_URL: URL}


async def test_options(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: 10})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_integration.options == {CONF_SCAN_INTERVAL: 10}
    await hass.async_block_till_done()
    assert setup_integration.runtime_data.update_interval.total_seconds() == 600
