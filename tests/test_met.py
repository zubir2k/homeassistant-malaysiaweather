"""Unit tests for the MET client and parsers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.malaysia_weather.met import (
    MetClient,
    nearest_station,
    normalize_name,
    parse_forecast,
    parse_marine,
    parse_met_datetime,
    parse_observations,
    stations_from_records,
)

from .conftest import KEY, MET, met_forecast_records, met_page, marine_records

KL = timezone(timedelta(hours=8))


def test_parse_met_datetime() -> None:
    """MET dates parse robustly."""
    assert parse_met_datetime("Sat 2026-10-31 7:31 AM (UTC+08:00)") == datetime(2026, 10, 31, 7, 31, tzinfo=KL)
    assert parse_met_datetime("Sat 2026-10-31 12:00 AM (UTC+08:00)") == datetime(2026, 10, 31, 0, 0, tzinfo=KL)
    assert parse_met_datetime("Sat 2026-10-31 12:15 PM (UTC+08:00)") == datetime(2026, 10, 31, 12, 15, tzinfo=KL)
    assert parse_met_datetime("Sat 2026-10-31 11:00 PM (UTC+0800)").hour == 23
    assert parse_met_datetime("2026-10-31T07:31:00").hour == 7
    assert parse_met_datetime("2026-10-31").tzinfo is not None
    for bad in (None, "", "soon", 5, "2026-13-45 1:00 AM"):
        assert parse_met_datetime(bad) is None


def test_normalize_name() -> None:
    """data.gov.my names match MET names."""
    assert normalize_name("Gombak (Taman Perwira )") == "GOMBAK"
    assert normalize_name("Fraser's Hill") == "FRASER S HILL"
    assert normalize_name("kajang") == "KAJANG"


def test_parse_forecast() -> None:
    """Seven days, six datatypes, issue time and location details."""
    data = parse_forecast(met_forecast_records() + [{"bad": 1}, "x"])
    assert len(data.days) == 7
    assert all(len(day) == 6 for day in data.days.values())
    today = data.day()
    assert today["FSIGW"] == "Thunderstorms"
    assert today["FMAXT"] == 33
    assert data.state == "SELANGOR"
    assert data.issued.hour == 7 and data.issued.minute == 31
    assert parse_forecast([]).day() is None


def test_parse_marine() -> None:
    """Only today's wind and waves, with units."""
    marine = parse_marine(marine_records(), None)
    assert marine == {
        "marine_area": "SELANGOR",
        "marine_wind_speed": "10-20 km/h",
        "marine_wind_direction": "E",
        "marine_wave_height": "0.5 - 1.0 m",
    }
    assert parse_marine([], "Selangor") is None


def test_observations_tolerant() -> None:
    """Missing fields, unknown units and other stations are tolerated."""
    records = [
        {"locationid": "S1", "datatype": "TEMP", "date": "Sat 2026-10-31 8:00 AM (UTC+08:00)", "value": "28"},
        {"locationid": "S1", "datatype": "WND_SPD", "date": "Sat 2026-10-31 8:00 AM (UTC+08:00)", "value": 10, "attributes": {"unit": "knots"}},
        {"locationid": "S1", "datatype": "WND_DIR", "date": "Sat 2026-10-31 8:00 AM (UTC+08:00)", "value": "NE", "attributes": None},
        {"locationid": "S1", "datatype": "VIS", "date": "Sat 2026-10-31 8:00 AM (UTC+08:00)", "value": 10},
        {"locationid": "S1", "datatype": "RH", "date": "Sat 2026-10-31 8:00 AM (UTC+08:00)", "value": None},
        {"locationid": "S2", "datatype": "TEMP", "date": "Sat 2026-10-31 9:00 AM (UTC+08:00)", "value": 40},
        {"locationid": "S1", "datatype": "UNKNOWN", "date": "Sat 2026-10-31 9:00 AM (UTC+08:00)", "value": 1},
    ]
    obs = parse_observations(records, "S1")
    assert obs.temperature == 28
    assert obs.wind_speed == 18.5
    assert obs.wind_bearing == "NE"
    assert obs.visibility == 10
    assert obs.humidity is None
    now = datetime(2026, 10, 31, 15, 0, tzinfo=KL)
    assert parse_observations(records, "S1", now=now, max_age=timedelta(hours=3)) is None
    assert parse_observations([], "S1") is None


def test_nearest_station() -> None:
    """Stations come from the records' coordinates."""
    records = [
        {"locationid": "A", "latitude": 6.1, "longitude": 100.4},
        {"locationid": "B", "latitude": "2.9", "longitude": "101.7"},
        {"locationid": "C", "latitude": None, "longitude": None},
    ]
    stations = stations_from_records(records)
    assert [s.id for s in stations] == ["A", "B"]
    assert nearest_station(stations, 2.99, 101.79).id == "B"
    assert nearest_station([], 0, 0) is None


async def test_find_location_paging_and_cache(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """TOWN is paged with offset; results are cached per Cache-Control."""
    page2 = [{"id": "LOCATION:288", "name": "KAJANG", "latitude": 2.99, "longitude": 101.79}]
    aioclient_mock.get(
        f"{MET}/locations?locationcategoryid=TOWN&offset=50",
        json=met_page(page2, count=51, offset=50),
        headers={"Cache-Control": "max-age=86400"},
    )
    aioclient_mock.get(
        f"{MET}/locations?locationcategoryid=TOWN",
        json=met_page([{"id": f"LOCATION:{i}", "name": f"TOWN {i}"} for i in range(50)], count=51),
        headers={"Cache-Control": "max-age=86400"},
    )
    client = MetClient(hass, KEY)
    found = await client.async_find_location("Tn082", "Kajang")
    assert found["id"] == "LOCATION:288"
    assert aioclient_mock.call_count == 2
    await client.async_find_location("Tn082", "Kajang")
    assert aioclient_mock.call_count == 2  # served from cache

    # A different key never reuses another key's cache
    await MetClient(hass, "other").async_find_location("Tn082", "Kajang")
    assert aioclient_mock.call_count == 4


async def test_find_location_fallback_categories(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A tourist destination matches loosely (Highland vs HIGHLANDS)."""
    aioclient_mock.get(
        f"{MET}/locations?locationcategoryid=TOURISTDEST",
        json=met_page([{"id": "LOCATION:9", "name": "CAMERON HIGHLANDS"}]),
    )
    aioclient_mock.get(f"{MET}/locations", json=met_page([]))
    client = MetClient(hass, KEY)
    found = await client.async_find_location("Rc008", "Cameron Highland")
    assert found["id"] == "LOCATION:9"
    # Preferred category first: only one call
    assert aioclient_mock.call_count == 1
    assert await client.async_find_location("Tn999", "Nowhere") is None


async def test_burst_limiter_spaces_requests(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The 10th request inside a minute waits instead of hitting MET's limit."""
    from unittest.mock import AsyncMock, patch

    aioclient_mock.get(f"{MET}/locations", json=met_page([]))
    client = MetClient(hass, KEY)
    with patch("custom_components.malaysia_weather.met.asyncio.sleep", new=AsyncMock()) as sleep:
        for _ in range(9):
            await client.async_get("locations", use_cache=False)
        sleep.assert_not_called()
        await client.async_get("locations", use_cache=False)
        sleep.assert_called_once()
