"""Weather platform for Malaysia Weather integration."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

import aiohttp
import async_timeout

from homeassistant.components.weather import (
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    FORECAST_URL,
    CONF_LOCATION_ID,
    CONF_LOCATION_NAME,
    UPDATE_INTERVAL_FORECAST,
    CONDITION_MAPPING,
    ATTRIBUTION,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Malaysia Weather platform."""
    # Skip setup for the warnings entry (empty data)
    if not config_entry.data:
        return

    location_id = config_entry.data[CONF_LOCATION_ID]
    location_name = config_entry.data[CONF_LOCATION_NAME]

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"malaysia_weather_{location_id}",
        update_method=lambda: fetch_weather_data(location_id),
        update_interval=timedelta(seconds=UPDATE_INTERVAL_FORECAST),
    )

    await coordinator.async_config_entry_first_refresh()

    async_add_entities([MalaysiaWeather(coordinator, location_id, location_name)])

async def fetch_weather_data(location_id: str) -> dict:
    """Fetch weather data from API."""
    async with async_timeout.timeout(10):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{FORECAST_URL}?contains={location_id}@location__location_id"
            ) as response:
                return await response.json()

class MalaysiaWeather(CoordinatorEntity, WeatherEntity):
    """Implementation of Malaysia Weather."""

    _attr_has_entity_name = True
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        location_id: str,
        location_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._location_id = location_id
        self._location_name = location_name
        self._attr_unique_id = f"malaysia_weather_{location_id}"
        self._attr_name = location_name

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        condition = self.condition
        if condition is None:
            return "mdi:weather-partly-cloudy"
        return f"mdi:weather-{condition}"

    @property
    def native_temperature(self) -> float | None:
        """Return the current temperature."""
        if not self.coordinator.data:
            return None
        try:
            return float(self.coordinator.data[0]["max_temp"])
        except (KeyError, IndexError, ValueError):
            return None

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        if not self.coordinator.data:
            return None
        try:
            forecast = self.coordinator.data[0]["summary_forecast"]
            return CONDITION_MAPPING.get(forecast, "unknown")
        except (KeyError, IndexError):
            return None

    async def async_forecast_daily(self) -> list[dict[str, Any]] | None:
        """Return the daily forecast."""
        if not self.coordinator.data:
            return None

        forecast_data = []
        for daily_data in self.coordinator.data:
            try:
                forecast_data.append({
                    "datetime": datetime.strptime(
                        daily_data["date"], "%Y-%m-%d"
                    ).date(),
                    "native_temperature": float(daily_data["max_temp"]),
                    "native_templow": float(daily_data["min_temp"]),
                    "condition": CONDITION_MAPPING.get(
                        daily_data["summary_forecast"], "unknown"
                    ),
                })
            except (KeyError, ValueError) as err:
                _LOGGER.error("Error parsing forecast data: %s", err)
                continue

        return forecast_data