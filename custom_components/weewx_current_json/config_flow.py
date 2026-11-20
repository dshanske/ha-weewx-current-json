"""Set up a station from the UI by the address of its current.json."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_URL
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import api
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import WeewxConfigEntry

_LOGGER = logging.getLogger(__name__)

# Example addresses, kept out of the translations, which may not contain URLs.
EXAMPLES = {
    "example_site": "weather.example.com",
    "example_file": "https://weather.example.com/current.json",
}

URL_SCHEMA = vol.Schema({vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL))})


class WeewxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a station by the address of its file."""

    VERSION = 1

    async def _validate(self, text: str) -> tuple[str, dict[str, Any] | None, dict[str, str]]:
        """Return (url, document, errors) for what the user typed."""
        url = api.normalize_url(text)
        try:
            document = await api.fetch(async_get_clientsession(self.hass), url)
        except api.CannotConnect as err:
            _LOGGER.debug("Cannot connect: %s", err)
            return url, None, {"base": "cannot_connect"}
        except api.FormatError as err:
            _LOGGER.debug("Not a current-conditions file: %s", err)
            return url, None, {"base": "invalid_format"}
        return url, document, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url, document, errors = await self._validate(user_input[CONF_URL])
            if document is not None:
                await self.async_set_unique_id(url.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=_title(document), data={CONF_URL: url})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(URL_SCHEMA, user_input),
            errors=errors,
            description_placeholders=EXAMPLES,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the address, such as when the station's site moves."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url, document, errors = await self._validate(user_input[CONF_URL])
            if document is not None:
                if any(
                    other.unique_id == url.lower()
                    for other in self._async_current_entries(include_ignore=False)
                    if other.entry_id != entry.entry_id
                ):
                    raise AbortFlow("already_configured")
                return self.async_update_reload_and_abort(entry, unique_id=url.lower(), data_updates={CONF_URL: url})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(URL_SCHEMA, user_input or {CONF_URL: entry.data[CONF_URL]}),
            errors=errors,
            description_placeholders=EXAMPLES,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: WeewxConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return WeewxOptionsFlow()


class WeewxOptionsFlow(OptionsFlow):
    """How often to fetch the file."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])})
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _title(document: dict[str, Any]) -> str:
    station = api.section(document, "station")
    return str(station.get("name") or station.get("id") or "WeeWX")
