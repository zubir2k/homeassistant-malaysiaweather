# Changelog

## v1.1.0

Requires Home Assistant 2024.11 or newer. Tested against HA 2026.11 changes.

### Added
- Optional MET Malaysia API key per location ("hybrid mode"). Without a key nothing changes: data.gov.my is the only source.
- With a key, the weather entity gains English forecast attributes (`summary_en`, `morning_forecast_en`, `afternoon_forecast_en`, `night_forecast_en`), `state`, `latitude`, `longitude` and `forecast_issued`. data.gov.my stays the forecast source.
- Optional marine area (MET WATERS) in the options: today's `marine_area`, `marine_wind_speed`, `marine_wind_direction` and `marine_wave_height`.
- Live observations for keys MET has granted observation access: temperature, humidity, wind speed, wind bearing and visibility from the nearest station, plus `precipitation_last_hour`. Falls back to the forecast when unavailable.
- Key is checked when saved (`invalid_api_key`, `cannot_connect`); observation access is probed on save and on every setup.
- Repair issues when MET rejects the key later (`met_api_key_invalid`) or keeps failing (`met_unavailable`); they clear themselves once MET answers again. A MET outage never makes the weather entity unavailable.
- Diagnostics, with the API key redacted.
- Tests (pytest-homeassistant-custom-component).

### Fixed
- Options flow (Change location) crashed on Home Assistant 2025.12 and newer (`property 'config_entry' has no setter`).
- Changing location now reloads the entry right away, updates its title and unique ID, and removes the old weather entity.
- Today's condition and temperature come from today's forecast, not the first row the API returns. Past days are dropped from the forecast.
- MET phrases that aren't in the mapping no longer report the invalid condition `unknown`; prefix fallbacks cover new wording (e.g. "Ribut petir ...", "Hujan ...").
- If the earthquake feed or an imagery URL is down at startup, the Warnings & Imagery entry still loads; only that entity goes unavailable.
- Warning sensors no longer use the `enum` device class without options. Earthquake magnitude and depth are numbers.

### Changed
- Ready for the HA 2026.11 entity naming: every entry now has a service device. Location weather entities take the location name; warnings, earthquake, imagery and the image entities sit on a "MET Malaysia" device with translated names.
- Existing entity IDs are kept (unique IDs are unchanged). New installs get IDs like `sensor.met_malaysia_weather_warning` and `select.met_malaysia_satellite_imagery`.
- One shared aiohttp session, `asyncio.timeout`, proper coordinators (`UpdateFailed` on HTTP errors), `entry.runtime_data`.
- Image entities are coordinator based, so no custom lifecycle hooks are needed for HA 2026.11's in-place entity ID changes.
- Location picker is a searchable dropdown.
- Bahasa Melayu translation added.
- Weather entity exposes today's raw MET wording (morning, afternoon, night) as attributes.
- `hacs.json` minimum HA set to 2024.11.0 for the Marketplace; manifest `categories` kept (`weather_alerts.forecasts`, `weather_alerts.public_warnings`).
- Options flow now covers location, MET API key and marine area.
- The MET location for each data.gov.my location is looked up once and cached in the entry.
- MET calls stay well under the 2,000/day limit: forecast every 3 hours, observations every 30 minutes, responses reused as MET's `Cache-Control` allows.
- New brand icon and logo images.
