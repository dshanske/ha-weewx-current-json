"""Tests for reading the file, without Home Assistant running."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.weewx_current_json import api


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("weather.example.com", "https://weather.example.com/current.json"),
        ("weather.example.com/", "https://weather.example.com/current.json"),
        ("  http://192.168.1.5/weewx  ", "http://192.168.1.5/weewx/current.json"),
        ("https://weather.example.com/data/now.json", "https://weather.example.com/data/now.json"),
        ("https://weather.example.com/current.json?x=1", "https://weather.example.com/current.json?x=1"),
    ],
)
def test_normalize_url(typed: str, expected: str) -> None:
    assert api.normalize_url(typed) == expected


def test_resolve() -> None:
    assert api.resolve("https://w.example.com/wx/current.json", "webcam.jpg") == "https://w.example.com/wx/webcam.jpg"
    assert api.resolve("https://w.example.com/current.json", "https://cam.example.com/a.jpg") == "https://cam.example.com/a.jpg"


def test_parse(document: dict[str, Any]) -> None:
    assert api.parse(document) is document
    del document["units"]
    assert api.parse(document) is document, "Metric is the default."


@pytest.mark.parametrize(
    "change",
    [
        {"format": "something-else"},
        {"version": 2},
        {"units": "us"},
        {"station": None},
        {"time": None},
        {"observations": []},
    ],
)
def test_parse_rejects(document: dict[str, Any], change: dict[str, Any]) -> None:
    document.update(change)
    with pytest.raises(api.FormatError):
        api.parse(document)


def test_parse_rejects_non_objects() -> None:
    for value in (None, [], "current-conditions", 1):
        with pytest.raises(api.FormatError):
            api.parse(value)


@pytest.mark.parametrize(
    ("code", "daytime", "condition"),
    [
        (800, True, "sunny"),
        (800, None, "sunny"),
        (800, False, "clear-night"),
        (801, False, "partlycloudy"),
        (802, True, "partlycloudy"),
        (803, True, "cloudy"),
        (804, True, "cloudy"),
        (500, True, "rainy"),
        (503, True, "rainy"),
        (504, True, "pouring"),
        (521, True, "rainy"),
        (511, True, "snowy-rainy"),
        (309, True, "snowy-rainy"),
        (301, True, "rainy"),
        (601, True, "snowy"),
        (616, True, "snowy-rainy"),
        (624, True, "hail"),
        (201, True, "lightning-rainy"),
        (211, True, "lightning"),
        (233, True, "hail"),
        (400, True, "windy"),
        (701, True, "fog"),
        (721, True, "fog"),
        (741, True, "fog"),
        (771, True, "windy"),
        (781, True, "exceptional"),
        (999, True, None),
        (None, True, None),
        ("800", True, None),
        (True, True, None),
    ],
)
def test_ha_condition(code: Any, daytime: bool | None, condition: str | None) -> None:
    assert api.ha_condition(code, daytime) == condition


def test_every_extension_code_has_a_condition() -> None:
    # Every code weewx-current-json 0.3 can write, from its conditions module.
    codes = (201, 211, 233, 300, 301, 302, 309, 400, 500, 503, 504, 511, 520, 521, 522, 600, 601, 602,
             611, 612, 616, 622, 624, 701, 711, 721, 741, 761, 762, 771, 781, 782, 800, 801, 802, 803, 804)
    assert [code for code in codes if api.ha_condition(code) is None] == []


def test_is_daytime(document: dict[str, Any]) -> None:
    assert api.is_daytime(document) is True
    document["time"] = document["almanac"]["sunset"] + 60
    assert api.is_daytime(document) is False
    del document["almanac"]
    assert api.is_daytime(document) is None


def test_generator_version(document: dict[str, Any]) -> None:
    assert api.generator_version(document) == "0.3.0"
    assert api.generator_version({}) is None
    assert api.generator_version({"generator": "something"}) is None


def test_number() -> None:
    assert api.number({"a": 1.5}, "a") == 1.5
    assert api.number({"a": True}, "a") is None
    assert api.number({"a": "1"}, "a") is None
    assert api.number(None, "a") is None
