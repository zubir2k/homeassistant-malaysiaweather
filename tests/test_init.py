"""Setup, MET extras, marine, observations and repair issues."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.malaysia_weather.const import (
    CONF_API_KEY,
    CONF_LOCATION_ID,
    CONF_LOCATION_NAME,
    CONF_MARINE_AREA,
    CONF_MARINE_AREA_NAME,
    CONF_MET_LOCATION_FOR,
    CONF_MET_LOCATION_ID,
    CONF_MET_OBSERVATION,
    CONF_MET_STATION_ID,
    DOMAIN,
)
from custom_components.malaysia_weather.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    KEY,
    MET,
    met_calls,
    met_page,
    mock_basic,
    mock_met,
)

ENTITY = "weather.kajang"


def _entry(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kajang",
        unique_id="Tn082",
        data={CONF_LOCATION_ID: "Tn082", CONF_LOCATION_NAME: "Kajang"},
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_without_key_is_unchanged(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """No key: data.gov.my only, same attributes as v1.1.0, no MET calls."""
    mock_basic(aioclient_mock)
    entry = _entry(hass)
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(ENTITY)
    assert state.state == "lightning-rainy"
    assert state.attributes["temperature"] == 33
    assert state.attributes["summary_forecast"] == "Ribut petir di beberapa tempat"
    for key in ("summary_en", "state", "latitude", "forecast_issued", "marine_area", "humidity"):
        assert key not in state.attributes
    assert met_calls(aioclient_mock, "") == 0
    assert aioclient_mock.call_count == 1
    assert entry.runtime_data.met is None


async def test_met_extras_and_location_mapping(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A normal key adds English text, state, coordinates and issue time."""
    mock_basic(aioclient_mock)
    mock_met(aioclient_mock)
    entry = _entry(hass, **{CONF_API_KEY: KEY, CONF_MET_OBSERVATION: False})
    await _setup(hass, entry)

    state = hass.states.get(ENTITY)
    assert state.state == "lightning-rainy"  # still data.gov.my
    attrs = state.attributes
    assert attrs["summary_forecast"] == "Ribut petir di beberapa tempat"  # Malay kept
    assert attrs["summary_en"] == "Thunderstorms"
    assert attrs["morning_forecast_en"] == "No Rain"
    assert attrs["afternoon_forecast_en"] == "Thunderstorms"
    assert attrs["night_forecast_en"] == "No Rain"
    assert attrs["state"] == "SELANGOR"
    assert attrs["latitude"] == 2.9927
    assert attrs["longitude"] == 101.7909
    issued = dt_util.parse_datetime(attrs["forecast_issued"])
    assert (issued.hour, issued.minute) == (7, 31)
    assert issued.utcoffset() == timedelta(hours=8)
    assert "marine_area" not in attrs
    assert "humidity" not in attrs  # no observation access

    # Mapping is cached in the entry
    assert entry.data[CONF_MET_LOCATION_ID] == "LOCATION:288"
    assert entry.data[CONF_MET_LOCATION_FOR] == "Tn082"
    assert entry.runtime_data.observation is None
    town_calls = met_calls(aioclient_mock, "locationcategoryid=TOWN")
    assert town_calls == 1
    # Only one forecast call: 42 records fit in one page
    assert met_calls(aioclient_mock, "datacategoryid=GENERAL") == 1

    # A refresh does not search MET locations again
    await entry.runtime_data.met.async_refresh()
    assert met_calls(aioclient_mock, "locationcategoryid=TOWN") == town_calls

    # No issues
    assert not ir.async_get(hass).issues

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["options"][CONF_API_KEY] == "**REDACTED**"
    assert KEY not in str(diag)
    assert diag["met_mode"] == "key"


async def test_unmatched_location_skips_met_extras(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """No MET match: entity works, mapping cached as empty, no forecast calls."""
    mock_basic(aioclient_mock)
    mock_met(aioclient_mock, towns=[])
    entry = _entry(hass, **{CONF_API_KEY: KEY})
    await _setup(hass, entry)

    state = hass.states.get(ENTITY)
    assert state.state == "lightning-rainy"
    assert "summary_en" not in state.attributes
    assert entry.data[CONF_MET_LOCATION_ID] == ""
    assert entry.data[CONF_MET_LOCATION_FOR] == "Tn082"
    assert met_calls(aioclient_mock, "datacategoryid=GENERAL") == 0
    searched = met_calls(aioclient_mock, "/locations")
    await entry.runtime_data.met.async_refresh()
    assert met_calls(aioclient_mock, "/locations") == searched


async def test_marine_attributes(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A marine area adds today's sea wind and waves as attributes only."""
    mock_basic(aioclient_mock)
    mock_met(aioclient_mock)
    entry = _entry(
        hass,
        **{
            CONF_API_KEY: KEY,
            CONF_MARINE_AREA: "LOCATION:495",
            CONF_MARINE_AREA_NAME: "Selangor",
        },
    )
    await _setup(hass, entry)

    attrs = hass.states.get(ENTITY).attributes
    assert attrs["marine_area"] == "Selangor"
    assert attrs["marine_wind_speed"] == "10-20 km/h"
    assert attrs["marine_wind_direction"] == "E"
    assert attrs["marine_wave_height"] == "0.5 - 1.0 m"
    assert "wind_speed" not in attrs  # never faked from the sea range


def _obs(station, datatype, value, unit=None, hours_ago=0, lat=3.0, lon=101.7, name=None):
    when = dt_util.now(dt_util.get_time_zone("Asia/Kuala_Lumpur")) - timedelta(hours=hours_ago)
    hour = when.replace(minute=0, second=0, microsecond=0)
    return {
        "locationid": station,
        "locationname": name or station,
        "date": f"{hour.strftime('%a %Y-%m-%d')} {hour.strftime('%I:%M %p').lstrip('0')} (UTC+08:00)",
        "datatype": datatype,
        "value": value,
        "latitude": lat,
        "longitude": lon,
        "attributes": {"unit": unit} if unit else {},
    }


async def test_observation_fills_native_values(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With observation access, the nearest station's latest reading is used."""
    mock_basic(aioclient_mock)
    # Discovery: two stations, the Subang-like one is nearer to Kajang
    aioclient_mock.get(
        f"{MET}/data?datasetid=OBSERVATION&locationid=ALL_LOCATIONS&datatypeid=TEMP",
        json=met_page(
            [
                _obs("LOCATION:FAR", "TEMP", 30, "C", lat=6.1, lon=100.4),
                _obs("LOCATION:NEAR", "TEMP", 29, "C", lat=3.0, lon=101.75),
            ]
        ),
    )
    readings = [
        _obs("LOCATION:NEAR", "TEMP", 25.0, "C", hours_ago=1, name="SEPANG"),
        _obs("LOCATION:NEAR", "TEMP", "27.4", "C", name="SEPANG"),
        _obs("LOCATION:NEAR", "RH", 81, "%"),
        _obs("LOCATION:NEAR", "WND_SPD", 5, "m/s"),
        _obs("LOCATION:NEAR", "WND_DIR", 230, "deg"),
        _obs("LOCATION:NEAR", "VIS", 9000, "m"),
        _obs("LOCATION:NEAR", "RAIN_1HR", 1.2, "mm"),
        _obs("LOCATION:NEAR", "PRST_WX_ID", "2"),
        {"locationid": "LOCATION:NEAR", "datatype": "TEMP"},  # malformed: ignored
    ]
    aioclient_mock.get(
        f"{MET}/data?datasetid=OBSERVATION&locationid=LOCATION:NEAR",
        json=met_page(readings),
    )
    mock_met(aioclient_mock, observation_status=200)
    entry = _entry(hass, **{CONF_API_KEY: KEY})
    await _setup(hass, entry)

    assert entry.options[CONF_MET_OBSERVATION] is True  # re-probed at setup
    assert entry.data[CONF_MET_STATION_ID] == "LOCATION:NEAR"
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["temperature"] == 27.4
    assert attrs["humidity"] == 81
    assert attrs["wind_speed"] == 18.0  # 5 m/s -> km/h
    assert attrs["wind_bearing"] == 230
    assert attrs["visibility"] == 9.0
    assert attrs["precipitation_last_hour"] == 1.2
    assert attrs["observation_station"] == "SEPANG"
    assert attrs["present_weather_id"] == "2"
    assert attrs["summary_en"] == "Thunderstorms"


async def test_observation_unavailable_falls_back(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Stale or missing observations fall back to the forecast maximum."""
    mock_basic(aioclient_mock)
    aioclient_mock.get(
        f"{MET}/data?datasetid=OBSERVATION&locationid=ALL_LOCATIONS&datatypeid=TEMP",
        json=met_page([_obs("LOCATION:NEAR", "TEMP", 29, "C")]),
    )
    aioclient_mock.get(
        f"{MET}/data?datasetid=OBSERVATION&locationid=LOCATION:NEAR",
        json=met_page([_obs("LOCATION:NEAR", "TEMP", 20, "C", hours_ago=5)]),
    )
    mock_met(aioclient_mock, observation_status=200)
    entry = _entry(hass, **{CONF_API_KEY: KEY})
    await _setup(hass, entry)

    attrs = hass.states.get(ENTITY).attributes
    assert attrs["temperature"] == 33
    assert "humidity" not in attrs


async def test_key_revoked_creates_repair_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A later 401 keeps the entity on data.gov.my and raises a repair issue."""
    mock_basic(aioclient_mock)
    mock_met(aioclient_mock)
    entry = _entry(hass, **{CONF_API_KEY: KEY})
    await _setup(hass, entry)
    issue_id = f"met_api_key_invalid_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

    aioclient_mock.clear_requests()
    hass.data.pop("malaysia_weather_met_cache", None)  # skip Cache-Control reuse
    mock_basic(aioclient_mock)
    aioclient_mock.get(f"{MET}/data", status=401, json={"detail": "Invalid token."})
    await entry.runtime_data.met.async_refresh()
    await hass.async_block_till_done()

    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "met_api_key_invalid"
    assert issue.translation_placeholders == {"location": "Kajang"}
    state = hass.states.get(ENTITY)
    assert state.state == "lightning-rainy"  # still available
    # Last good MET values are kept
    assert state.attributes["summary_en"] == "Thunderstorms"

    # Key works again: issue cleared
    aioclient_mock.clear_requests()
    hass.data.pop("malaysia_weather_met_cache", None)
    mock_basic(aioclient_mock)
    mock_met(aioclient_mock)
    await entry.runtime_data.met.async_refresh()
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_key_rejected_at_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 401 during setup: entity loads in basic mode with a repair issue."""
    mock_basic(aioclient_mock)
    aioclient_mock.get(f"{MET}/data", status=401, json={"detail": "Invalid token."})
    entry = _entry(hass, **{CONF_API_KEY: KEY})
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.met is None
    assert hass.states.get(ENTITY).state == "lightning-rainy"
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, f"met_api_key_invalid_{entry.entry_id}"
    )


async def test_met_outage_never_breaks_entity(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Repeated MET errors raise a warning issue; the entity stays available."""
    mock_basic(aioclient_mock)
    aioclient_mock.get(f"{MET}/data?datasetid=OBSERVATION", exc=TimeoutError())
    aioclient_mock.get(f"{MET}/locations", status=500)
    entry = _entry(hass, **{CONF_API_KEY: KEY})
    await _setup(hass, entry)

    assert hass.states.get(ENTITY).state == "lightning-rainy"
    met = entry.runtime_data.met
    issue_id = f"met_unavailable_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    await met.async_refresh()
    await met.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    assert hass.states.get(ENTITY).state == "lightning-rainy"
    assert "summary_en" not in hass.states.get(ENTITY).attributes
