"""Read a weewx-current-json file.

Nothing here imports Home Assistant, so the format rules can be tested on their own. The file
format, "current-conditions" version 1, is defined by the weewx-current-json extension's README:
https://github.com/dshanske/weewx-current-json
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp

FORMAT = "current-conditions"
SUPPORTED_VERSION = 1
UNITS = "metric"
DEFAULT_FILENAME = "current.json"
TIMEOUT = 30


class WeewxError(Exception):
    """The file couldn't be read."""


class CannotConnect(WeewxError):
    """The station's web server couldn't be reached, or didn't return the file."""


class FormatError(WeewxError):
    """The file isn't a current-conditions file this integration can read."""


def normalize_url(text: str) -> str:
    """Return the file's address from what the user typed.

    Like the Android app: adds https:// without a scheme, and /current.json when the path doesn't
    name a .json file, so "weather.example.com" is enough.
    """
    url = text.strip()
    if "://" not in url:
        url = "https://" + url
    if not urlsplit(url).path.endswith(".json"):
        url = url.rstrip("/") + "/" + DEFAULT_FILENAME
    return url


def resolve(file_url: str, address: str) -> str:
    """Return an address the file gives, such as the webcam's, made absolute against the file's."""
    return urljoin(file_url, address.strip())


def parse(document: Any) -> dict[str, Any]:
    """Return the document if it's a current-conditions file this integration can read.

    Raises:
        FormatError: Not a JSON object, another format, a version other than 1 or units other
            than metric.
    """
    if not isinstance(document, dict) or not isinstance(document.get("station"), dict):
        raise FormatError("Not a weewx-current-json file")
    if document.get("format") != FORMAT:
        raise FormatError(f"Unknown format {document.get('format')!r}")
    if document.get("version") != SUPPORTED_VERSION:
        raise FormatError(f"Unsupported format version {document.get('version')!r}")
    if document.get("units", UNITS) != UNITS:
        raise FormatError(f"Unsupported units {document.get('units')!r}")
    if not isinstance(document.get("time"), (int, float)):
        raise FormatError("The file has no time")
    if not isinstance(document.get("observations", {}), dict):
        raise FormatError("The observations aren't an object")
    return document


async def fetch(session: aiohttp.ClientSession, url: str, timeout: float = TIMEOUT) -> dict[str, Any]:
    """Fetch and parse the file.

    The body is decoded as JSON whatever its content type, since web servers often serve .json
    files as text/plain.
    """
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"Accept": "application/json"},
        ) as response:
            response.raise_for_status()
            text = await response.text()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise CannotConnect(f"Could not fetch {url}: {err}") from err
    try:
        document = json.loads(text)
    except ValueError as err:
        raise FormatError(f"{url} isn't JSON") from err
    return parse(document)


def number(section: Any, key: str) -> float | None:
    """Return a number from a section of the file, or None if it's missing or not a number."""
    if not isinstance(section, dict):
        return None
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def section(document: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a section of the file, or an empty one."""
    value = document.get(key)
    return value if isinstance(value, dict) else {}


# Home Assistant's weather conditions, by name, so this module needn't import Home Assistant.
CLEAR_NIGHT = "clear-night"
CLOUDY = "cloudy"
EXCEPTIONAL = "exceptional"
FOG = "fog"
HAIL = "hail"
LIGHTNING = "lightning"
LIGHTNING_RAINY = "lightning-rainy"
PARTLYCLOUDY = "partlycloudy"
POURING = "pouring"
RAINY = "rainy"
SNOWY = "snowy"
SNOWY_RAINY = "snowy-rainy"
SUNNY = "sunny"
WINDY = "windy"

# Condition codes with a meaning of their own. The extension's codes are OpenWeatherMap-style, but
# 500, 503 and 504 are light, moderate and heavy rain, and 400 is windy, as in Simple Location.
_CODES = {
    233: HAIL,          # Thunderstorm with hail.
    309: SNOWY_RAINY,   # Freezing drizzle.
    400: WINDY,
    502: POURING,
    504: POURING,
    522: POURING,
    531: POURING,
    624: HAIL,
    702: EXCEPTIONAL,   # Frost.
    703: EXCEPTIONAL,   # Icy.
    771: WINDY,         # Squalls.
    772: EXCEPTIONAL,   # Waterspouts.
    781: EXCEPTIONAL,   # Tornado.
    782: EXCEPTIONAL,   # Hurricane or tropical storm.
    790: LIGHTNING,
    801: PARTLYCLOUDY,
    802: PARTLYCLOUDY,
    803: CLOUDY,
    804: CLOUDY,
    900: RAINY,         # Unknown precipitation.
}


def ha_condition(code: Any, daytime: bool | None = None) -> str | None:
    """Return Home Assistant's weather condition for a condition code, or None for an unknown one.

    Args:
        code: The file's condition code.
        daytime: Whether it's day, for clear skies; None is taken as day.
    """
    if isinstance(code, bool) or not isinstance(code, (int, float)):
        return None
    code = int(code)
    if code == 800:
        return CLEAR_NIGHT if daytime is False else SUNNY
    if code in _CODES:
        return _CODES[code]
    if code in (200, 201, 202, 230, 231, 232):
        return LIGHTNING_RAINY
    if 200 <= code < 300:
        return LIGHTNING
    if 300 <= code < 400:
        return RAINY
    if 511 <= code <= 513:
        return SNOWY_RAINY
    if 500 <= code < 600:
        return RAINY
    if 611 <= code <= 616:
        return SNOWY_RAINY
    if 600 <= code < 700:
        return SNOWY
    if 700 <= code < 770:
        # Mist, smoke, haze, dust, fog, sand and ash all hide the sky.
        return FOG
    return None


def is_daytime(document: dict[str, Any]) -> bool | None:
    """Return whether the file's time is between the day's sunrise and sunset, or None without them."""
    almanac = section(document, "almanac")
    sunrise = number(almanac, "sunrise")
    sunset = number(almanac, "sunset")
    time = number(document, "time")
    if sunrise is None or sunset is None or time is None:
        return None
    return sunrise <= time < sunset


def generator_version(document: dict[str, Any]) -> str | None:
    """Return the extension's version from "generator", such as 0.3.0, or None."""
    generator = document.get("generator")
    if not isinstance(generator, str):
        return None
    first = generator.split(";", 1)[0].split()
    return first[1] if len(first) == 2 else None
