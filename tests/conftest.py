"""Fixtures for Malaysia Weather tests."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from custom_components.malaysia_weather.met import met_today

pytest_plugins = "pytest_homeassistant_custom_component"

try:  # pycares starts a shutdown thread on first use; start it before any test
    import pycares

    pycares._shutdown_manager.start()  # noqa: SLF001
except (ImportError, AttributeError):  # pragma: no cover
    pass

FORECAST_URL = "https://api.data.gov.my/weather/forecast"
MET = "https://api.met.gov.my/v2.1"
KEY = "test-met-key-0123456789"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in every test."""
    yield


@pytest.fixture(autouse=True)
async def malaysia_time_zone(hass):
    """Run Home Assistant on Malaysian time, like a real install."""
    await hass.config.async_set_time_zone("Asia/Kuala_Lumpur")


def met_date(offset: int = 0, clock: str = "12:00 AM") -> str:
    """A MET style date string, e.g. 'Sat 2026-10-31 12:00 AM (UTC+08:00)'."""
    day = met_today() + timedelta(days=offset)
    return f"{day.strftime('%a')} {day.isoformat()} {clock} (UTC+08:00)"


def dgm_forecast(location_id: str = "Tn082", name: str = "Kajang") -> list[dict[str, Any]]:
    """data.gov.my 7-day forecast for one location."""
    return [
        {
            "location": {"location_id": location_id, "location_name": name},
            "date": (met_today() + timedelta(days=i)).isoformat(),
            "morning_forecast": "Tiada hujan",
            "afternoon_forecast": "Ribut petir di beberapa tempat",
            "night_forecast": "Tiada hujan",
            "summary_forecast": "Ribut petir di beberapa tempat",
            "summary_when": "Petang",
            "min_temp": 24,
            "max_temp": 33,
        }
        for i in range(7)
    ]


def met_page(results: list[dict[str, Any]], count: int | None = None, offset: int = 0) -> dict:
    """Wrap results like MET's paged responses."""
    return {
        "metadata": {
            "resultset": {
                "count": len(results) if count is None else count,
                "offset": offset,
                "limit": 50,
            }
        },
        "results": results,
    }


def met_forecast_records(location_id: str = "LOCATION:288") -> list[dict[str, Any]]:
    """MET FORECAST/GENERAL records for 7 days (42 records)."""
    values = {
        "FGM": "No Rain",
        "FGA": "Thunderstorms",
        "FGN": "No Rain",
        "FSIGW": "Thunderstorms",
        "FMAXT": 33,
        "FMINT": 24,
    }
    records = []
    for datatype, value in values.items():
        for day in range(7):
            records.append(
                {
                    "locationid": location_id,
                    "locationname": "KAJANG",
                    "locationrootid": "LOCATION:15",
                    "locationrootname": "SELANGOR",
                    "date": met_date(day),
                    "datatype": datatype,
                    "value": value,
                    "latitude": 2.9927,
                    "longitude": 101.7909,
                    "attributes": {
                        "ref": None,
                        "valid_from": met_date(0, "7:31 AM") if datatype in ("FGM", "FGA", "FGN") else None,
                        "valid_to": None,
                    },
                }
            )
    return records


TOWNS = [
    {"id": "LOCATION:122", "name": "AYER HITAM", "locationcategoryid": "TOWN", "latitude": 1.915, "longitude": 103.18},
    {"id": "LOCATION:288", "name": "KAJANG", "locationcategoryid": "TOWN", "latitude": 2.9927, "longitude": 101.7909},
]

WATERS = [
    {"id": "LOCATION:495", "name": "SELANGOR", "locationcategoryid": "WATERS", "latitude": None, "longitude": None},
    {"id": "LOCATION:665", "name": "MELAKA", "locationcategoryid": "WATERS", "latitude": None, "longitude": None},
]


def marine_records() -> list[dict[str, Any]]:
    """MET FORECAST/MARINE records for today, as seen live."""
    base = {"locationid": "LOCATION:495", "locationname": "SELANGOR", "date": met_date(0), "latitude": None, "longitude": None}
    return [
        {**base, "datatype": "FMM", "value": "Isolated thunderstorms", "attributes": {}},
        {**base, "datatype": "FMWD", "value": "E", "attributes": {}},
        {**base, "datatype": "FMWS", "value": "10-20", "attributes": {"unit": "km/h"}},
        {**base, "datatype": "FMWH", "value": "0.5 - 1.0", "attributes": {"unit": "m"}},
        # Tomorrow must be ignored
        {**base, "date": met_date(1), "datatype": "FMWS", "value": "30-40", "attributes": {"unit": "km/h"}},
    ]


def mock_basic(aioclient_mock, location_id: str = "Tn082") -> None:
    """data.gov.my forecast."""
    aioclient_mock.get(FORECAST_URL, json=dgm_forecast(location_id))


def mock_met(
    aioclient_mock,
    *,
    observation_status: int = 403,
    towns: list | None = None,
    forecast: list | None = None,
) -> None:
    """MET endpoints for a normal key."""
    aioclient_mock.get(
        f"{MET}/data?datasetid=OBSERVATION&locationid=ALL_LOCATIONS",
        status=observation_status,
        json={"detail": "You do not have permission to perform this action."}
        if observation_status == 403
        else met_page([]),
    )
    aioclient_mock.get(
        f"{MET}/locations?locationcategoryid=TOWN",
        json=met_page(TOWNS if towns is None else towns),
        headers={"Cache-Control": "max-age=86400"},
    )
    aioclient_mock.get(
        f"{MET}/locations?locationcategoryid=WATERS",
        json=met_page(WATERS),
        headers={"Cache-Control": "max-age=86400"},
    )
    for category in ("DISTRICT", "TOURISTDEST", "DIVISION"):
        aioclient_mock.get(
            f"{MET}/locations?locationcategoryid={category}", json=met_page([])
        )
    aioclient_mock.get(
        f"{MET}/locations?locationcategoryid=STATE",
        json=met_page([{"id": "LOCATION:15", "name": "SELANGOR", "locationcategoryid": "STATE"}]),
    )
    aioclient_mock.get(
        f"{MET}/data?datasetid=FORECAST&datacategoryid=GENERAL",
        json=met_page(met_forecast_records() if forecast is None else forecast),
        headers={"Cache-Control": "max-age=60"},
    )
    aioclient_mock.get(
        f"{MET}/data?datasetid=FORECAST&datacategoryid=MARINE",
        json=met_page(marine_records()),
    )


def met_calls(aioclient_mock, fragment: str) -> int:
    """How many requests went to MET URLs containing fragment."""
    return sum(
        1 for _, url, _, _ in aioclient_mock.mock_calls if "api.met.gov.my" in str(url) and fragment in str(url)
    )
