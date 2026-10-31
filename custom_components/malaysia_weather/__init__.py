"""The Malaysia Weather integration."""
from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_API_KEY, CONF_LOCATION_ID, CONF_MET_OBSERVATION, SATELLITE_URLS
from .coordinator import (
    ForecastCoordinator,
    ImageryCoordinator,
    LocationRuntimeData,
    MalaysiaWeatherConfigEntry,
    MetForecastCoordinator,
    MetHealth,
    MetObservationCoordinator,
    WarningsRuntimeData,
    async_clear_met_issues,
    async_report_met_auth_error,
    earthquake_coordinator,
    warnings_coordinator,
)
from .met import MetAuthError, MetClient, MetError

_LOGGER = logging.getLogger(__name__)

LOCATION_PLATFORMS: list[Platform] = [Platform.WEATHER]
WARNINGS_PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT, Platform.IMAGE]


def is_warnings_entry(entry: MalaysiaWeatherConfigEntry) -> bool:
    """Return True for the data-less Warnings & Imagery entry."""
    return CONF_LOCATION_ID not in entry.data


def _platforms(entry: MalaysiaWeatherConfigEntry) -> list[Platform]:
    return WARNINGS_PLATFORMS if is_warnings_entry(entry) else LOCATION_PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: MalaysiaWeatherConfigEntry) -> bool:
    """Set up Malaysia Weather from a config entry."""
    if is_warnings_entry(entry):
        runtime = WarningsRuntimeData(
            warnings=warnings_coordinator(hass, entry),
            earthquake=earthquake_coordinator(hass, entry),
            imagery={
                name: ImageryCoordinator(hass, entry, name, url)
                for name, url in SATELLITE_URLS.items()
            },
        )
        # Warnings must load; the others may be down without blocking setup
        await runtime.warnings.async_config_entry_first_refresh()
        await runtime.earthquake.async_refresh()
        for coordinator in runtime.imagery.values():
            await coordinator.async_refresh()
        entry.runtime_data = runtime
    else:
        location_id = entry.data[CONF_LOCATION_ID]
        # After a location change, drop the old weather entity left in the registry
        registry = er.async_get(hass)
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg_entry.unique_id != f"malaysia_weather_{location_id}":
                registry.async_remove(reg_entry.entity_id)
        forecast = ForecastCoordinator(hass, entry, location_id)
        await forecast.async_config_entry_first_refresh()
        runtime = LocationRuntimeData(forecast=forecast)
        await _async_setup_met(hass, entry, runtime)
        entry.runtime_data = runtime

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))
    return True


async def _async_setup_met(
    hass: HomeAssistant, entry: MalaysiaWeatherConfigEntry, runtime: LocationRuntimeData
) -> None:
    """Add the optional MET coordinators. Nothing here may block setup."""
    api_key = (entry.options.get(CONF_API_KEY) or "").strip()
    if not api_key:
        async_clear_met_issues(hass, entry)
        return

    client = MetClient(hass, api_key)
    observation = bool(entry.options.get(CONF_MET_OBSERVATION))
    # Re-probe observation access; MET may grant or withdraw it at any time
    try:
        observation = await client.async_probe_observation()
    except MetAuthError:
        _LOGGER.warning(
            "MET Malaysia rejected the API key for %s; using data.gov.my only", entry.title
        )
        async_report_met_auth_error(hass, entry)
        return
    except MetError as err:
        _LOGGER.debug("Could not probe MET observation access, keeping last result: %s", err)
    else:
        if observation != bool(entry.options.get(CONF_MET_OBSERVATION)):
            hass.config_entries.async_update_entry(
                entry, options={**entry.options, CONF_MET_OBSERVATION: observation}
            )

    health = MetHealth(hass, entry)
    runtime.met = MetForecastCoordinator(hass, entry, client, health)
    await runtime.met.async_refresh()
    if observation:
        runtime.observation = MetObservationCoordinator(hass, entry, client, health)
        await runtime.observation.async_refresh()


async def async_remove_entry(hass: HomeAssistant, entry: MalaysiaWeatherConfigEntry) -> None:
    """Drop repair issues of a removed entry."""
    async_clear_met_issues(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: MalaysiaWeatherConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _platforms(entry))
