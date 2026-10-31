"""Data update coordinators for Malaysia Weather."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_LOCATION_ID,
    CONF_LOCATION_NAME,
    CONF_MARINE_AREA,
    CONF_MARINE_AREA_NAME,
    CONF_MET_LATITUDE,
    CONF_MET_LOCATION_FOR,
    CONF_MET_LOCATION_ID,
    CONF_MET_LONGITUDE,
    CONF_MET_STATION_ID,
    DOMAIN,
    EARTHQUAKE_URL,
    FORECAST_URL,
    ISSUE_MET_API_KEY_INVALID,
    ISSUE_MET_UNAVAILABLE,
    MET_FAILURES_BEFORE_ISSUE,
    MET_FORECAST_DAYS,
    MET_OBSERVATION_MAX_AGE,
    REQUEST_TIMEOUT,
    UPDATE_INTERVAL_FORECAST,
    UPDATE_INTERVAL_IMAGERY,
    UPDATE_INTERVAL_MET_FORECAST,
    UPDATE_INTERVAL_MET_OBSERVATION,
    UPDATE_INTERVAL_WARNINGS,
    WARNING_URL,
)
from .met import (
    MetAuthError,
    MetClient,
    MetError,
    MetForbiddenError,
    MetForecastData,
    ObservationData,
    nearest_station,
    parse_forecast,
    parse_marine,
    parse_observations,
    stations_from_records,
)

_LOGGER = logging.getLogger(__name__)


async def async_fetch_json(
    hass: HomeAssistant, url: str, params: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Fetch a JSON list from data.gov.my using the shared session."""
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise UpdateFailed(f"{url} returned HTTP {response.status}")
                data = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise UpdateFailed(f"Error communicating with {url}: {err}") from err
    except ValueError as err:
        raise UpdateFailed(f"Invalid JSON from {url}: {err}") from err

    if not isinstance(data, list):
        raise UpdateFailed(f"Unexpected payload from {url}")
    return data


class MalaysiaWeatherCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Generic coordinator that polls one data.gov.my endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        name: str,
        url: str,
        interval: timedelta,
        params: dict[str, str] | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=name,
            update_interval=interval,
        )
        self._url = url
        self._params = params

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data from the API."""
        return await async_fetch_json(self.hass, self._url, self._params)


class ForecastCoordinator(MalaysiaWeatherCoordinator):
    """Seven-day forecast for one location, sorted and trimmed to today onward."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, location_id: str) -> None:
        """Initialize the forecast coordinator."""
        super().__init__(
            hass,
            entry,
            name=f"malaysia_weather_{location_id}",
            url=FORECAST_URL,
            interval=UPDATE_INTERVAL_FORECAST,
            params={"contains": f"{location_id}@location__location_id"},
        )

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch, sort and drop days that have already passed."""
        data = await super()._async_update_data()
        if not data:
            raise UpdateFailed("No forecast returned for this location")
        today = dt_util.now().date().isoformat()
        days = sorted(
            (day for day in data if isinstance(day.get("date"), str)),
            key=lambda day: day["date"],
        )
        upcoming = [day for day in days if day["date"] >= today]
        return upcoming or days


def warnings_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> MalaysiaWeatherCoordinator:
    """Coordinator for MET weather warnings."""
    return MalaysiaWeatherCoordinator(
        hass, entry, "malaysia_weather_warnings", WARNING_URL, UPDATE_INTERVAL_WARNINGS
    )


def earthquake_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> MalaysiaWeatherCoordinator:
    """Coordinator for MET earthquake warnings."""
    return MalaysiaWeatherCoordinator(
        hass, entry, "malaysia_weather_earthquake", EARTHQUAKE_URL, UPDATE_INTERVAL_WARNINGS
    )


@dataclass
class ImageData:
    """Latest bytes of one imagery feed."""

    content: bytes
    fingerprint: str


class ImageryCoordinator(DataUpdateCoordinator[ImageData]):
    """Poll one MET imagery URL."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, name: str, url: str) -> None:
        """Initialize the imagery coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"malaysia_weather_image_{name}",
            update_interval=UPDATE_INTERVAL_IMAGERY,
        )
        self.url = url

    async def _async_update_data(self) -> ImageData:
        """Download the image."""
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with session.get(self.url) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"{self.url} returned HTTP {response.status}")
                    content = await response.read()
                    fingerprint = (
                        response.headers.get("ETag")
                        or response.headers.get("Last-Modified")
                        or str(hash(content))
                    )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error fetching {self.url}: {err}") from err
        return ImageData(content=content, fingerprint=fingerprint)


def met_issue_id(entry: ConfigEntry, kind: str) -> str:
    """Repair issue id for one entry."""
    return f"{kind}_{entry.entry_id}"


def async_clear_met_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove any MET repair issues for this entry."""
    for kind in (ISSUE_MET_API_KEY_INVALID, ISSUE_MET_UNAVAILABLE):
        ir.async_delete_issue(hass, DOMAIN, met_issue_id(entry, kind))


def async_report_met_auth_error(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The key was rejected: ask the user to update it in the options."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        met_issue_id(entry, ISSUE_MET_API_KEY_INVALID),
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_MET_API_KEY_INVALID,
        translation_placeholders={"location": entry.title},
    )


class MetHealth:
    """Shared failure tracking for an entry's MET coordinators.

    MET problems never fail the weather entity; they only raise repair
    issues so the user knows the extras are missing.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self._hass = hass
        self._entry = entry
        self.failures = 0

    def success(self) -> None:
        """MET answered: clear issues."""
        self.failures = 0
        async_clear_met_issues(self._hass, self._entry)

    def auth_failed(self) -> None:
        """MET rejected the key (HTTP 401)."""
        _LOGGER.warning(
            "MET Malaysia rejected the API key for %s; using data.gov.my only",
            self._entry.title,
        )
        ir.async_delete_issue(
            self._hass, DOMAIN, met_issue_id(self._entry, ISSUE_MET_UNAVAILABLE)
        )
        async_report_met_auth_error(self._hass, self._entry)

    def failed(self, err: Exception) -> None:
        """MET errored; raise an issue after repeated failures."""
        self.failures += 1
        _LOGGER.debug("MET request failed (%s in a row): %s", self.failures, err)
        if self.failures >= MET_FAILURES_BEFORE_ISSUE:
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                met_issue_id(self._entry, ISSUE_MET_UNAVAILABLE),
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_MET_UNAVAILABLE,
                translation_placeholders={"location": self._entry.title},
            )


class _MetCoordinator[T](DataUpdateCoordinator[T | None]):
    """Base for MET coordinators: errors go to MetHealth, never to the entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: MetClient,
        health: MetHealth,
        name: str,
        interval: timedelta,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=name,
            update_interval=interval,
        )
        self.client = client
        self.health = health

    async def _async_fetch(self) -> T | None:
        raise NotImplementedError

    async def _async_update_data(self) -> T | None:
        try:
            data = await self._async_fetch()
        except MetAuthError as err:
            self.health.auth_failed()
            raise UpdateFailed("MET API key rejected") from err
        except MetError as err:
            self.health.failed(err)
            raise UpdateFailed(str(err)) from err
        self.health.success()
        return data


class MetForecastCoordinator(_MetCoordinator[MetForecastData]):
    """English forecast, state, coordinates and marine extras from MET."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MetClient, health: MetHealth
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            entry,
            client,
            health,
            name=f"malaysia_weather_met_{entry.data[CONF_LOCATION_ID]}",
            interval=UPDATE_INTERVAL_MET_FORECAST,
        )

    async def _async_met_location(self) -> str | None:
        """MET location id for this entry, searched once and cached in entry.data."""
        entry = self.config_entry
        location_id = entry.data[CONF_LOCATION_ID]
        if entry.data.get(CONF_MET_LOCATION_FOR) == location_id:
            return entry.data.get(CONF_MET_LOCATION_ID) or None

        name = entry.data.get(CONF_LOCATION_NAME, entry.title)
        found = await self.client.async_find_location(location_id, name)
        new_data = {
            **entry.data,
            CONF_MET_LOCATION_FOR: location_id,
            CONF_MET_LOCATION_ID: found["id"] if found else "",
            CONF_MET_LATITUDE: found.get("latitude") if found else None,
            CONF_MET_LONGITUDE: found.get("longitude") if found else None,
        }
        new_data.pop(CONF_MET_STATION_ID, None)
        if found:
            _LOGGER.debug("Mapped %s (%s) to MET %s", name, location_id, found["id"])
        else:
            _LOGGER.debug("No MET location matches %s (%s); skipping MET extras", name, location_id)
        self.hass.config_entries.async_update_entry(entry, data=new_data)
        return found["id"] if found else None

    async def _async_fetch(self) -> MetForecastData:
        met_location = await self._async_met_location()
        data = MetForecastData()
        if met_location:
            data = parse_forecast(
                await self.client.async_forecast(met_location, MET_FORECAST_DAYS)
            )
            if data.latitude is None:
                data.latitude = self.config_entry.data.get(CONF_MET_LATITUDE)
                data.longitude = self.config_entry.data.get(CONF_MET_LONGITUDE)

        options = self.config_entry.options
        if waters := options.get(CONF_MARINE_AREA):
            data.marine = parse_marine(
                await self.client.async_marine(waters), options.get(CONF_MARINE_AREA_NAME)
            )
        return data


class MetObservationCoordinator(_MetCoordinator[ObservationData]):
    """Latest hourly observation from the nearest MET station (needs access)."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MetClient, health: MetHealth
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            entry,
            client,
            health,
            name=f"malaysia_weather_met_obs_{entry.data[CONF_LOCATION_ID]}",
            interval=UPDATE_INTERVAL_MET_OBSERVATION,
        )

    async def _async_station(self) -> str | None:
        """Nearest station id, found once from observation records and cached."""
        entry = self.config_entry
        if station := entry.data.get(CONF_MET_STATION_ID):
            return station
        lat = entry.data.get(CONF_MET_LATITUDE)
        lon = entry.data.get(CONF_MET_LONGITUDE)
        if lat is None or lon is None:
            return None
        # One-off discovery: TEMP records across all stations carry their coordinates
        records = await self.client.async_observations(
            "ALL_LOCATIONS", datatype="TEMP", max_pages=20
        )
        station = nearest_station(stations_from_records(records), float(lat), float(lon))
        if station is None:
            _LOGGER.debug("No MET observation station with coordinates found")
            return None
        _LOGGER.debug("Nearest MET station for %s is %s", entry.title, station.id)
        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_MET_STATION_ID: station.id}
        )
        return station.id

    async def _async_fetch(self) -> ObservationData | None:
        try:
            station = await self._async_station()
            if station is None:
                return None
            records = await self.client.async_observations(station)
        except MetForbiddenError:
            _LOGGER.debug("MET observation access is no longer granted for this key")
            return None
        return parse_observations(
            records, station, now=dt_util.utcnow(), max_age=MET_OBSERVATION_MAX_AGE
        )


@dataclass
class LocationRuntimeData:
    """Runtime data for a location entry."""

    forecast: ForecastCoordinator
    met: MetForecastCoordinator | None = None
    observation: MetObservationCoordinator | None = None


@dataclass
class WarningsRuntimeData:
    """Runtime data for the Warnings & Imagery entry."""

    warnings: MalaysiaWeatherCoordinator
    earthquake: MalaysiaWeatherCoordinator
    imagery: dict[str, ImageryCoordinator] = field(default_factory=dict)


type MalaysiaWeatherConfigEntry = ConfigEntry[LocationRuntimeData | WarningsRuntimeData]
