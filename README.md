# WeeWX Current Conditions for Home Assistant

A Home Assistant integration for [WeeWX](https://weewx.com) weather stations that run the
[weewx-current-json](https://github.com/dshanske/weewx-current-json) extension. Each archive
interval, the extension writes `current.json` beside the station's web pages. This integration
reads that file and gives the station:

* a **weather entity**, with the current condition, such as "partly cloudy" or "rainy", and the
  National Weather Service hourly and twice-daily forecasts when the station runs
  [weewx-nws](https://github.com/chaunceygardiner/weewx-nws);
* **sensors** for each reading the station has: temperature, humidity, pressure, wind, rain, snow,
  solar radiation, UV, air quality and the AQI, lightning and more, plus today's highs, lows and
  totals, the temperature and pressure trend, the current storm, and indoor and extra sensors;
* a **weather alerts** binary sensor, with weewx-nws, and an event for each new alert;
* **battery and signal** diagnostics from the station's hardware.

The station needn't be on your network. Any `current.json` that Home Assistant can fetch works,
including a friend's station or one across the country.

## Requirements

* Home Assistant 2026.10 or later.
* A WeeWX station with weewx-current-json 0.3 or later installed, with its web pages reachable from
  Home Assistant.

## Installation

### Marketplace

1. In Home Assistant, open **Marketplace**.
2. Open the menu (⋮), choose **Custom repositories**, and add
   `https://github.com/dshanske/ha-weewx-current-json` as an **Integration**.
3. Find **WeeWX Current Conditions** and install it.

### By hand

Copy `custom_components/weewx_current_json` into the `custom_components` folder of your Home
Assistant configuration, then restart Home Assistant.

## Setup

Go to **Settings → Devices & services → Add integration** and choose **WeeWX Current
Conditions**. Enter the address of the station's file, such as
`https://weather.example.com/current.json`. The station's web address alone, such as
`weather.example.com`, is enough when the file is at its top level: the integration adds
`https://` and `/current.json` when they're missing.

Add the integration again for each station. To change a station's address later, choose
**Reconfigure** on its entry.

### Options

* **Update interval**: minutes between fetches, 5 by default. WeeWX writes the file every archive
  interval, which is five minutes unless you've changed it, so fetching more often gains nothing.

## Entities

The integration creates entities only for what the station's file has, and adds more if new
readings appear later. Values are in metric units, as in the file, and Home Assistant converts them
to your unit system.

### Weather

The weather entity's condition is the one the extension derives, from the station's own sensors,
a nearby airport's METAR or the NWS forecast, as set up in WeeWX. Clear skies are "clear, night"
between sunset and sunrise. With weewx-nws, the entity has hourly and twice-daily forecasts, which
you can read with the `weather.get_forecasts` action.

### Sensors

| Group | Sensors |
|---|---|
| Current | Temperature, humidity, dew point, heat index, wind chill, apparent temperature, cloud base, pressure, wind speed, gust and direction, rain and snow in the last hour, rain and snow rate, snow depth, solar radiation, illuminance, UV index, cloud cover, PM1, PM2.5, PM10, CO, CO₂, ozone, sulphur dioxide, ammonia, lead, VOC and NOx indices, AQI (with its category and color as attributes), lightning strikes in the last hour and their distance |
| Today | High and low (with the time of each as an attribute), highest gust, rain, snow, evapotranspiration, wind run, lightning strikes, heating, cooling and growing degree days |
| Trend | Temperature and pressure change over the last few hours (3 by default, in the `hours` attribute) |
| Rain | Rain in the last 24 hours, the current storm's rain (with its start), and when it last rained |
| Indoor | Indoor temperature, humidity and dew point, when the station shares them |
| Extra sensors | Each extra temperature, humidity, soil and leaf sensor, by the name set in WeeWX |
| Diagnostics | Hardware warnings (with their messages), signal strength and each voltage |

The temperature trend stays in °C, because converting a change of temperature to °F would add 32.

### Binary sensors

* **Weather alerts**, with weewx-nws: on while NWS has an active alert for the station. Its
  `alerts` attribute lists each one with its event, headline, severity, urgency, certainty, area,
  description, instruction and times.
* **Battery** sensors, one per battery the hardware reports, on when the extension warns that it's
  low. The extension knows how each WeeWX driver reports a low battery.

### Alert events

Each alert that appears after Home Assistant starts fires a `weewx_current_json_alert` event once,
with the alert's keys, the station's name and the config entry's id. For example, to be notified:

```yaml
automation:
  - alias: "Weather alert"
    triggers:
      - trigger: event
        event_type: weewx_current_json_alert
    actions:
      - action: notify.notify
        data:
          title: "{{ trigger.event.data.event }}"
          message: "{{ trigger.event.data.headline }}"
```

## Troubleshooting

* **Could not fetch the file**: open the address in a browser from the same network as Home
  Assistant. The file is written by WeeWX's report engine into its `HTML_ROOT`, so it must be
  published wherever your web pages are.
* **Not a weewx-current-json file**: the address returns something else, or a file in another
  format, version or unit system. The integration reads version 1 in metric units.
* Diagnostics, downloaded from the integration's entry, hold the latest file with the station's
  address and coordinates removed.

## Development

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff check .
pytest -q
```

`custom_components/weewx_current_json/api.py` reads and checks the file without Home Assistant.
The file format is defined in the weewx-current-json README.

## License

GPL-3.0-or-later, like weewx-current-json. See [LICENSE](LICENSE).
