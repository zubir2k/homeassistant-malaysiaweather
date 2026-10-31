"""Client and parsers for the optional MET Malaysia API (api.met.gov.my).

Everything here is best effort: callers fall back to data.gov.my when MET
is unavailable, so the weather entity never depends on this module.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import logging
from math import asin, cos, radians, sin, sqrt
import re
import time
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    MET_API_URL,
    MET_CATEGORY_BY_PREFIX,
    MET_LOCATION_CATEGORIES,
    MET_OBSERVATION_TYPES,
    MET_PAGE_LIMIT,
    MET_TIMEZONE,
    REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

MET_TZ = ZoneInfo(MET_TIMEZONE)
_CACHE_KEY = f"{DOMAIN}_met_cache"
_LIMITER_KEY = f"{DOMAIN}_met_limiter"
# MET allows bursts of 10 requests a minute; keep one spare
BURST_LIMIT = 9
BURST_WINDOW = 60.0


class _BurstLimiter:
    """Space out MET requests so a burst never passes MET's per-minute limit."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sent: deque[float] = deque()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            while self._sent and now - self._sent[0] >= BURST_WINDOW:
                self._sent.popleft()
            if len(self._sent) >= BURST_LIMIT:
                wait = BURST_WINDOW - (now - self._sent[0])
                _LOGGER.debug("Waiting %.0fs to stay under MET's burst limit", wait)
                await asyncio.sleep(wait)
                self._sent.popleft()
            self._sent.append(time.monotonic())


class MetError(Exception):
    """Base error for the MET API."""


class MetAuthError(MetError):
    """The API key was rejected (HTTP 401)."""


class MetForbiddenError(MetError):
    """The key is valid but has no access to this dataset (HTTP 403)."""


class MetConnectionError(MetError):
    """Timeout, connection problem, rate limit or unexpected response."""


def met_today() -> date:
    """Today's date in Malaysia, whatever Home Assistant's time zone is."""
    return dt_util.now(MET_TZ).date()


# "Sat 2026-10-31 7:31 AM (UTC+08:00)"
_MET_DATE_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:[ T]+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
    r"\s*(?P<ampm>[AaPp][Mm])?)?"
    r"(?:\s*\(?\s*(?:UTC|GMT)\s*(?P<tz>[+-]\d{1,2}(?::?\d{2})?)\s*\)?)?"
)


def parse_met_datetime(value: Any) -> datetime | None:
    """Parse a MET date string into an aware datetime; None when unparseable."""
    if not isinstance(value, str) or not value.strip():
        return None
    match = _MET_DATE_RE.search(value)
    if match is None:
        return None
    try:
        day = date.fromisoformat(match["date"])
        hour = int(match["hour"] or 0)
        minute = int(match["minute"] or 0)
        second = int(match["second"] or 0)
        ampm = (match["ampm"] or "").upper()
        if ampm == "PM" and hour < 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
        tzinfo: Any = MET_TZ
        if match["tz"]:
            raw = match["tz"].replace(":", "")
            sign = -1 if raw[0] == "-" else 1
            digits = raw[1:]
            hours = int(digits[:-2] or 0) if len(digits) > 2 else int(digits)
            minutes = int(digits[-2:]) if len(digits) > 2 else 0
            tzinfo = timezone(sign * timedelta(hours=hours, minutes=minutes))
        return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=tzinfo)
    except ValueError:
        return None


def normalize_name(name: Any) -> str:
    """Normalise a location name for matching: upper case, no brackets."""
    if not isinstance(name, str):
        return ""
    name = name.split("(")[0]
    name = re.sub(r"[^A-Za-z0-9]+", " ", name)
    return " ".join(name.upper().split())


def _loose(name: str) -> str:
    """Looser form: ignore a plural S on each word (Highland/Highlands)."""
    return " ".join(word[:-1] if word.endswith("S") and len(word) > 3 else word for word in name.split())


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _max_age(cache_control: str | None) -> int:
    """Seconds a response may be reused according to Cache-Control."""
    if not cache_control:
        return 0
    lowered = cache_control.lower()
    if "no-store" in lowered or "no-cache" in lowered:
        return 0
    match = re.search(r"max-age\s*=\s*(\d+)", lowered)
    return int(match.group(1)) if match else 0


class MetClient:
    """Small async client for api.met.gov.my using HA's shared session."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        """Initialize the client. The key is never logged."""
        self._hass = hass
        self._api_key = api_key
        # Responses are cached per key so one key can't validate another
        self._key_id = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        self.calls = 0

    def _cache(self) -> dict[tuple, tuple[float, Any]]:
        return self._hass.data.setdefault(_CACHE_KEY, {})

    async def async_get(
        self, path: str, params: dict[str, Any] | None = None, *, use_cache: bool = True
    ) -> dict[str, Any]:
        """GET one MET endpoint and return its JSON object."""
        params = {k: str(v) for k, v in (params or {}).items()}
        cache_key = (self._key_id, path, tuple(sorted(params.items())))
        cache = self._cache()
        if use_cache and (hit := cache.get(cache_key)) and hit[0] > time.monotonic():
            return hit[1]

        limiter: _BurstLimiter = self._hass.data.setdefault(_LIMITER_KEY, _BurstLimiter())
        await limiter.acquire()
        session = async_get_clientsession(self._hass)
        url = f"{MET_API_URL}/{path}"
        headers = {"Authorization": f"METToken {self._api_key}"}
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with session.get(url, params=params, headers=headers) as response:
                    self.calls += 1
                    if response.status == 401:
                        raise MetAuthError("MET API key rejected")
                    if response.status == 403:
                        raise MetForbiddenError(f"No access to MET {path}")
                    if response.status != 200:
                        raise MetConnectionError(f"MET {path} returned HTTP {response.status}")
                    data = await response.json(content_type=None)
                    max_age = _max_age(response.headers.get("Cache-Control"))
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MetConnectionError(f"Error communicating with MET {path}: {err}") from err
        except ValueError as err:
            raise MetConnectionError(f"Invalid JSON from MET {path}") from err

        if not isinstance(data, dict):
            raise MetConnectionError(f"Unexpected payload from MET {path}")
        if max_age > 0:
            cache[cache_key] = (time.monotonic() + max_age, data)
        return data

    async def async_get_all(
        self, path: str, params: dict[str, Any] | None = None, *, max_pages: int = 5
    ) -> list[dict[str, Any]]:
        """GET every page (limit 50, offset paging) up to max_pages."""
        results: list[dict[str, Any]] = []
        offset = 0
        for _ in range(max_pages):
            page_params = dict(params or {})
            if offset:
                page_params["offset"] = offset
            data = await self.async_get(path, page_params)
            page = [item for item in data.get("results") or [] if isinstance(item, dict)]
            results.extend(page)
            resultset = (data.get("metadata") or {}).get("resultset") or {}
            count = resultset.get("count")
            limit = resultset.get("limit") or MET_PAGE_LIMIT
            offset += limit
            if not page or not isinstance(count, int) or offset >= count:
                break
        return results

    async def async_validate(self) -> None:
        """Raise MetAuthError/MetConnectionError when the key does not work."""
        await self.async_get(
            "locations", {"locationcategoryid": "STATE"}, use_cache=False
        )

    async def async_probe_observation(self) -> bool:
        """True when the key may read hourly observations (most get 403)."""
        today = met_today().isoformat()
        try:
            await self.async_get(
                "data",
                {
                    "datasetid": "OBSERVATION",
                    "datacategoryid": "HOURLY",
                    "locationid": "ALL_LOCATIONS",
                    "start_date": today,
                    "end_date": today,
                },
                use_cache=False,
            )
        except MetForbiddenError:
            return False
        return True

    async def async_locations(self, category: str) -> list[dict[str, Any]]:
        """All MET locations of one category (cached per Cache-Control)."""
        return await self.async_get_all(
            "locations", {"locationcategoryid": category}, max_pages=20
        )

    async def async_find_location(
        self, location_id: str, location_name: str
    ) -> dict[str, Any] | None:
        """Find the MET location for a data.gov.my location by name."""
        wanted = normalize_name(location_name)
        if not wanted:
            return None
        preferred = MET_CATEGORY_BY_PREFIX.get(location_id[:2])
        categories = [preferred] if preferred else []
        categories += [c for c in MET_LOCATION_CATEGORIES if c != preferred]
        for category in categories:
            candidates = [
                item for item in await self.async_locations(category) if item.get("id")
            ]
            for item in candidates:
                if normalize_name(item.get("name")) == wanted:
                    return item
            for item in candidates:
                if _loose(normalize_name(item.get("name"))) == _loose(wanted):
                    return item
        return None

    async def async_forecast(self, met_location_id: str, days: int) -> list[dict[str, Any]]:
        """General forecast (FGM/FGA/FGN/FSIGW/FMAXT/FMINT) in English."""
        start = met_today()
        return await self.async_get_all(
            "data",
            {
                "datasetid": "FORECAST",
                "datacategoryid": "GENERAL",
                "locationid": met_location_id,
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=days - 1)).isoformat(),
                "lang": "en",
            },
            max_pages=3,
        )

    async def async_marine(self, waters_id: str) -> list[dict[str, Any]]:
        """Today's marine forecast for one WATERS area."""
        today = met_today().isoformat()
        return await self.async_get_all(
            "data",
            {
                "datasetid": "FORECAST",
                "datacategoryid": "MARINE",
                "locationid": waters_id,
                "start_date": today,
                "end_date": today,
                "lang": "en",
            },
            max_pages=1,
        )

    async def async_observations(
        self, location_id: str, *, datatype: str | None = None, max_pages: int = 6
    ) -> list[dict[str, Any]]:
        """Today's hourly observations for one station (or ALL_LOCATIONS)."""
        today = met_today().isoformat()
        params = {
            "datasetid": "OBSERVATION",
            "datacategoryid": "HOURLY",
            "locationid": location_id,
            "start_date": today,
            "end_date": today,
        }
        if datatype:
            params["datatypeid"] = datatype
        return await self.async_get_all("data", params, max_pages=max_pages)


# --------------------------------------------------------------------------
# Parsers (pure functions, unit tested)


@dataclass
class MetForecastData:
    """Parsed MET extras for one location."""

    days: dict[str, dict[str, Any]] = field(default_factory=dict)
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    issued: datetime | None = None
    marine: dict[str, Any] | None = None

    def day(self, when: date | None = None) -> dict[str, Any] | None:
        """Values for one day (default today in Malaysia, else the next one)."""
        key = (when or met_today()).isoformat()
        if key in self.days:
            return self.days[key]
        upcoming = sorted(k for k in self.days if k >= key)
        return self.days[upcoming[0]] if upcoming else None


def parse_forecast(records: list[dict[str, Any]]) -> MetForecastData:
    """Group MET GENERAL forecast records by day and datatype."""
    data = MetForecastData()
    for record in records:
        if not isinstance(record, dict):
            continue
        when = parse_met_datetime(record.get("date"))
        datatype = record.get("datatype")
        if when is None or not isinstance(datatype, str):
            continue
        data.days.setdefault(when.date().isoformat(), {})[datatype] = record.get("value")
        if data.state is None and record.get("locationrootname"):
            data.state = record["locationrootname"]
        if data.latitude is None:
            data.latitude = _to_float(record.get("latitude"))
            data.longitude = _to_float(record.get("longitude"))
        attributes = record.get("attributes")
        if isinstance(attributes, dict) and datatype in ("FGM", "FGA", "FGN"):
            issued = parse_met_datetime(attributes.get("valid_from"))
            if issued and (data.issued is None or issued > data.issued):
                data.issued = issued
    return data


def _with_unit(value: Any, attributes: Any) -> str | None:
    if value is None or value == "":
        return None
    unit = attributes.get("unit") if isinstance(attributes, dict) else None
    return f"{value} {unit}" if unit else str(value)


def parse_marine(records: list[dict[str, Any]], area_name: str | None) -> dict[str, Any] | None:
    """Today's marine wind and waves; None when MET returned nothing usable."""
    today = met_today()
    found: dict[str, Any] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        when = parse_met_datetime(record.get("date"))
        if when is not None and when.date() != today:
            continue
        datatype = record.get("datatype")
        if datatype == "FMWS":
            found["marine_wind_speed"] = _with_unit(record.get("value"), record.get("attributes"))
        elif datatype == "FMWD":
            found["marine_wind_direction"] = record.get("value")
        elif datatype == "FMWH":
            found["marine_wave_height"] = _with_unit(record.get("value"), record.get("attributes"))
        if not area_name and record.get("locationname"):
            area_name = record["locationname"]
    if not found:
        return None
    return {"marine_area": area_name, **found}


@dataclass
class Station:
    """An observation station seen in /data records."""

    id: str
    name: str | None
    latitude: float
    longitude: float


def stations_from_records(records: list[dict[str, Any]]) -> list[Station]:
    """Unique stations with coordinates from observation records."""
    stations: dict[str, Station] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        station_id = record.get("locationid")
        lat = _to_float(record.get("latitude"))
        lon = _to_float(record.get("longitude"))
        if not station_id or lat is None or lon is None or station_id in stations:
            continue
        stations[station_id] = Station(station_id, record.get("locationname"), lat, lon)
    return list(stations.values())


def nearest_station(stations: list[Station], lat: float, lon: float) -> Station | None:
    """Closest station to a point."""
    if not stations:
        return None
    return min(stations, key=lambda s: distance_km(lat, lon, s.latitude, s.longitude))


@dataclass
class ObservationData:
    """Latest hourly observation at one station, in HA native units."""

    station_id: str
    station_name: str | None = None
    observed: datetime | None = None
    temperature: float | None = None
    humidity: float | None = None
    wind_speed: float | None = None  # km/h
    wind_bearing: float | str | None = None
    visibility: float | None = None  # km
    precipitation: float | None = None  # mm
    present_weather_id: Any = None


def _unit(record: dict[str, Any]) -> str:
    attributes = record.get("attributes")
    unit = attributes.get("unit") if isinstance(attributes, dict) else None
    return str(unit).strip().lower() if unit else ""


def _wind_kmh(value: float, unit: str) -> float:
    unit = unit.replace(" ", "")
    if unit in ("m/s", "ms-1", "ms^-1", "mps", "m s-1"):
        return round(value * 3.6, 1)
    if unit in ("knot", "knots", "kt", "kts", "kn"):
        return round(value * 1.852, 1)
    if unit in ("mph",):
        return round(value * 1.609344, 1)
    return value


def _visibility_km(value: float, unit: str) -> float:
    if unit in ("m", "meter", "meters", "metre", "metres"):
        return round(value / 1000, 2)
    if not unit and value > 100:  # unlabelled metres
        return round(value / 1000, 2)
    return value


def parse_observations(
    records: list[dict[str, Any]], station_id: str, now: datetime | None = None, max_age: timedelta | None = None
) -> ObservationData | None:
    """Latest value of each hourly datatype for one station."""
    latest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    name: str | None = None
    for record in records:
        if not isinstance(record, dict) or record.get("locationid") != station_id:
            continue
        datatype = record.get("datatype")
        when = parse_met_datetime(record.get("date"))
        if datatype not in MET_OBSERVATION_TYPES or when is None:
            continue
        if record.get("value") is None or record.get("value") == "":
            continue
        name = name or record.get("locationname")
        if datatype not in latest or when > latest[datatype][0]:
            latest[datatype] = (when, record)
    if not latest:
        return None

    observed = max(when for when, _ in latest.values())
    if now is not None and max_age is not None and now - observed > max_age:
        _LOGGER.debug("Latest MET observation at %s is too old (%s)", station_id, observed)
        return None

    data = ObservationData(station_id=station_id, station_name=name, observed=observed)
    for datatype, (_, record) in latest.items():
        value = record.get("value")
        number = _to_float(value)
        unit = _unit(record)
        if datatype == "TEMP":
            data.temperature = number
        elif datatype == "RH" and number is not None:
            data.humidity = number
        elif datatype == "WND_SPD" and number is not None:
            data.wind_speed = _wind_kmh(number, unit)
        elif datatype == "WND_DIR":
            data.wind_bearing = number if number is not None else (str(value).strip() or None)
        elif datatype == "VIS" and number is not None:
            data.visibility = _visibility_km(number, unit)
        elif datatype == "RAIN_1HR":
            data.precipitation = number
        elif datatype == "PRST_WX_ID":
            data.present_weather_id = value
    return data
