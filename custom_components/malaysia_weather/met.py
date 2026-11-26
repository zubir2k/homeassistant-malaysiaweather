"""Client and parsers for MET Malaysia re-exported from python-metmalaysia."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from metmalaysia import (
    EARTHQUAKE_URL,
    FORECAST_URL,
    MET_API_URL,
    MET_TZ,
    MetAuthError,
    MetConnectionError,
    MetError,
    MetForbiddenError,
    MetForecastData,
    MetMalaysiaClient,
    ObservationData,
    RADAR_URL,
    SATELLITE_URL,
    Station,
    WARNING_URL,
    distance_km,
    get_met_tz,
    loose_name,
    met_today,
    nearest_station,
    normalize_name,
    parse_forecast,
    parse_marine,
    parse_met_datetime,
    parse_observations,
    stations_from_records,
)

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "EARTHQUAKE_URL",
    "FORECAST_URL",
    "MET_API_URL",
    "MET_TZ",
    "MetAuthError",
    "MetClient",
    "MetConnectionError",
    "MetError",
    "MetForbiddenError",
    "MetForecastData",
    "ObservationData",
    "RADAR_URL",
    "SATELLITE_URL",
    "Station",
    "WARNING_URL",
    "distance_km",
    "get_met_tz",
    "loose_name",
    "met_today",
    "nearest_station",
    "normalize_name",
    "parse_forecast",
    "parse_marine",
    "parse_met_datetime",
    "parse_observations",
    "stations_from_records",
]


class MetClient(MetMalaysiaClient):
    """Home Assistant compatible wrapper around MetMalaysiaClient."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        """Initialize MetClient with Home Assistant session."""
        session = async_get_clientsession(hass)
        super().__init__(api_key=api_key, session=session)
        self._hass = hass
