"""Sensor platform for Malaysia Weather integration."""
from __future__ import annotations

from datetime import timedelta
import logging

import aiohttp
import async_timeout

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    WARNING_URL,
    EARTHQUAKE_URL,
    UPDATE_INTERVAL_WARNINGS,
    ATTRIBUTION,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Malaysia Weather warning sensors."""
    # Only set up warning sensors for the warnings entry (empty data)
    if entry.data:
        return

    warning_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="malaysia_weather_warnings",
        update_method=fetch_warning_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL_WARNINGS),
    )

    earthquake_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="malaysia_weather_earthquake",
        update_method=fetch_earthquake_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL_WARNINGS),
    )

    await warning_coordinator.async_config_entry_first_refresh()
    await earthquake_coordinator.async_config_entry_first_refresh()

    async_add_entities([
        WeatherWarningSensor(warning_coordinator),
        EarthquakeWarningSensor(earthquake_coordinator)
    ])

async def fetch_warning_data() -> dict:
    """Fetch warning data from API."""
    async with async_timeout.timeout(10):
        async with aiohttp.ClientSession() as session:
            async with session.get(WARNING_URL) as response:
                return await response.json()

async def fetch_earthquake_data() -> dict:
    """Fetch earthquake data from API."""
    async with async_timeout.timeout(10):
        async with aiohttp.ClientSession() as session:
            async with session.get(EARTHQUAKE_URL) as response:
                return await response.json()

class WeatherWarningSensor(CoordinatorEntity, SensorEntity):
    """Implementation of Malaysia Weather Warning sensor."""

    _attr_has_entity_name = True
    _attr_name = "Weather Warning"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "malaysia_weather_warning"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        try:
            return self.coordinator.data[0]["heading_en"]
        except (KeyError, IndexError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional warning information."""
        if not self.coordinator.data or not self.coordinator.data[0]:
            return {}
        
        warning = self.coordinator.data[0]
        return {
            "valid_from": warning.get("valid_from"),
            "valid_to": warning.get("valid_to"),
            "text": warning.get("text_en"),
            "instruction": warning.get("instruction_en"),
        }

class EarthquakeWarningSensor(CoordinatorEntity, SensorEntity):
    """Implementation of Malaysia Earthquake Warning sensor."""

    _attr_has_entity_name = True
    _attr_name = "Earthquake Warning"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "malaysia_earthquake_warning"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        try:
            return self.coordinator.data[0]["status"]
        except (KeyError, IndexError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional earthquake information."""
        if not self.coordinator.data or not self.coordinator.data[0]:
            return {}
        
        quake = self.coordinator.data[0]
        return {
            "magnitude": quake.get("magdefault"),
            "depth": quake.get("depth"),
            "location": quake.get("location_original"),
            "distance_from_malaysia": quake.get("n_distancemas"),
            "datetime": quake.get("localdatetime"),
        }
