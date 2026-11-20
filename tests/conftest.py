"""Fixtures for the tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.weewx_current_json.const import DOMAIN

URL = "https://weather.example.com/current.json"
DOCUMENT: dict[str, Any] = json.loads((Path(__file__).parent / "fixtures" / "current.json").read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture
def document() -> dict[str, Any]:
    """A fresh copy of the example file, to change in a test."""
    return copy.deepcopy(DOCUMENT)


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A station's config entry."""
    entry = MockConfigEntry(domain=DOMAIN, title="Backyard Weather", unique_id=URL, data={CONF_URL: URL})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    document: dict[str, Any],
) -> MockConfigEntry:
    """The station, set up from the example file."""
    aioclient_mock.get(URL, text=json.dumps(document))
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
