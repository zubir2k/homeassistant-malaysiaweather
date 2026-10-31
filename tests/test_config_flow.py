"""Config and options flow with the optional MET key."""
from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
import pytest
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
    DOMAIN,
)
from custom_components.malaysia_weather.coordinator import async_report_met_auth_error

from .conftest import FORECAST_URL, KEY, MET, dgm_forecast, mock_met

LOCATIONS = dgm_forecast("Tn082", "Kajang") + dgm_forecast("Tn155", "Gombak (Taman Perwira )")


@pytest.fixture
def no_setup():
    """Do not set up entries created by the flows."""
    with patch(
        "custom_components.malaysia_weather.async_setup_entry", return_value=True
    ) as mock:
        yield mock


def _warnings_entry(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, title="Warnings & Imagery", unique_id="warnings", data={}).add_to_hass(hass)


async def _location_form(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "location"
    return result


async def test_location_without_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_setup
) -> None:
    """The key is optional; leaving it out gives basic mode."""
    _warnings_entry(hass)
    aioclient_mock.get(FORECAST_URL, json=LOCATIONS)
    result = await _location_form(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCATION_ID: "Tn082"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_LOCATION_ID: "Tn082", CONF_LOCATION_NAME: "Kajang"}
    assert result["options"] == {}


async def test_location_key_validation(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_setup
) -> None:
    """401 -> invalid_api_key, timeout -> cannot_connect, valid + 403 -> key mode."""
    _warnings_entry(hass)
    aioclient_mock.get(FORECAST_URL, json=LOCATIONS)
    aioclient_mock.get(f"{MET}/locations", status=401, json={"detail": "Invalid token."})
    result = await _location_form(hass)
    # The key field is a masked password selector
    schema = result["data_schema"].schema
    key_selector = next(v for k, v in schema.items() if k == CONF_API_KEY)
    assert key_selector.config["type"] == "password"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCATION_ID: "Tn082", CONF_API_KEY: "bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_API_KEY: "invalid_api_key"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(FORECAST_URL, json=LOCATIONS)
    aioclient_mock.get(f"{MET}/locations", exc=TimeoutError())
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCATION_ID: "Tn082", CONF_API_KEY: KEY}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    mock_met(aioclient_mock, observation_status=403)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCATION_ID: "Tn082", CONF_API_KEY: f"  {KEY} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_API_KEY: KEY, CONF_MET_OBSERVATION: False}
    # The Authorization header uses the METToken scheme
    headers = [h for _, url, _, h in aioclient_mock.mock_calls if "locations" in str(url)]
    assert headers[0]["Authorization"] == f"METToken {KEY}"


async def test_location_key_with_observation_access(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_setup
) -> None:
    """A key that passes the observation probe stores the capability."""
    _warnings_entry(hass)
    aioclient_mock.get(FORECAST_URL, json=LOCATIONS)
    mock_met(aioclient_mock, observation_status=200)
    result = await _location_form(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOCATION_ID: "Tn082", CONF_API_KEY: KEY}
    )
    assert result["options"] == {CONF_API_KEY: KEY, CONF_MET_OBSERVATION: True}


def _location_entry(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kajang",
        unique_id="Tn082",
        data={
            CONF_LOCATION_ID: "Tn082",
            CONF_LOCATION_NAME: "Kajang",
            CONF_MET_LOCATION_ID: "LOCATION:288",
            CONF_MET_LOCATION_FOR: "Tn082",
        },
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


async def test_options_add_key_and_marine(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_setup
) -> None:
    """Adding a key leads to the optional marine area step."""
    entry = _location_entry(hass)
    aioclient_mock.get(FORECAST_URL, json=LOCATIONS)
    mock_met(aioclient_mock)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCATION_ID: "Tn082", CONF_API_KEY: KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "marine"
    # WATERS have no coordinates, so the default is none
    marine_key = next(k for k in result["data_schema"].schema if k == CONF_MARINE_AREA)
    assert marine_key.default() == "none"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MARINE_AREA: "LOCATION:495"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_API_KEY: KEY,
        CONF_MET_OBSERVATION: False,
        CONF_MARINE_AREA: "LOCATION:495",
        CONF_MARINE_AREA_NAME: "Selangor",
    }
    # Same location: cached MET mapping kept
    assert entry.data[CONF_MET_LOCATION_ID] == "LOCATION:288"


async def test_options_remove_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_setup
) -> None:
    """Clearing the key returns to basic mode and clears repair issues."""
    entry = _location_entry(
        hass, **{CONF_API_KEY: KEY, CONF_MET_OBSERVATION: False, CONF_MARINE_AREA: "LOCATION:495"}
    )
    async_report_met_auth_error(hass, entry)
    aioclient_mock.get(FORECAST_URL, json=LOCATIONS)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    # The current key is suggested (masked), so the user can clear it
    key = next(k for k in result["data_schema"].schema if k == CONF_API_KEY)
    assert key.description == {"suggested_value": KEY}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCATION_ID: "Tn082", CONF_API_KEY: ""}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {}
    assert not ir.async_get(hass).issues
    assert not any("api.met.gov.my" in str(url) for _, url, _, _ in aioclient_mock.mock_calls)


async def test_options_invalid_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_setup
) -> None:
    """A rejected key keeps the old options."""
    entry = _location_entry(hass)
    aioclient_mock.get(FORECAST_URL, json=LOCATIONS)
    aioclient_mock.get(f"{MET}/locations", status=401, json={})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCATION_ID: "Tn082", CONF_API_KEY: "bad"}
    )
    assert result["errors"] == {CONF_API_KEY: "invalid_api_key"}
    assert entry.options == {}


async def test_options_change_location_drops_met_cache(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_setup
) -> None:
    """A new location forgets the old MET mapping so it is searched again."""
    entry = _location_entry(hass)
    aioclient_mock.get(FORECAST_URL, json=LOCATIONS)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LOCATION_ID: "Tn155"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.title == "Gombak"
    assert entry.unique_id == "Tn155"
    assert CONF_MET_LOCATION_ID not in entry.data
    assert CONF_MET_LOCATION_FOR not in entry.data
