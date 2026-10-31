"""Weather platform for Malaysia Weather integration."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, ATTRIBUTION_MET, CONF_LOCATION_ID, map_condition
from .coordinator import (
    ForecastCoordinator,
    LocationRuntimeData,
    MalaysiaWeatherConfigEntry,
    MetForecastCoordinator,
    MetObservationCoordinator,
)
from .entity import location_device_info
from .met import MetForecastData, ObservationData

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MalaysiaWeatherConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the weather entity for a location entry."""
    runtime = entry.runtime_data
    if not isinstance(runtime, LocationRuntimeData):
        return
    async_add_entities(
        [MalaysiaWeather(runtime.forecast, entry, runtime.met, runtime.observation)]
    )


class MalaysiaWeather(CoordinatorEntity[ForecastCoordinator], WeatherEntity):
    """Seven-day MET forecast for one location."""

    _attr_has_entity_name = True
    _attr_name = None  # takes the device (location) name
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: ForecastCoordinator,
        entry: MalaysiaWeatherConfigEntry,
        met: MetForecastCoordinator | None = None,
        observation: MetObservationCoordinator | None = None,
    ) -> None:
        """Initialize the weather entity.

        data.gov.my stays the forecast source and decides availability; the
        optional MET coordinators only add attributes and live readings.
        """
        super().__init__(coordinator)
        location_id = entry.data[CONF_LOCATION_ID]
        # Unchanged from v1.0.x so existing entity IDs are kept
        self._attr_unique_id = f"malaysia_weather_{location_id}"
        self._attr_device_info = location_device_info(entry)
        self._met = met
        self._observation = observation
        if met is not None:
            self._attr_attribution = ATTRIBUTION_MET

    async def async_added_to_hass(self) -> None:
        """Also follow the MET coordinators."""
        await super().async_added_to_hass()
        for extra in (self._met, self._observation):
            if extra is not None:
                self.async_on_remove(extra.async_add_listener(self._handle_extra_update))

    @callback
    def _handle_extra_update(self) -> None:
        self.async_write_ha_state()

    @property
    def _met_data(self) -> MetForecastData | None:
        """Last good MET forecast (kept through later failures)."""
        return self._met.data if self._met is not None else None

    @property
    def _obs(self) -> ObservationData | None:
        """Latest MET observation, if the key has observation access."""
        return self._observation.data if self._observation is not None else None

    @property
    def _today(self) -> dict[str, Any] | None:
        """Forecast for today (the coordinator drops past days)."""
        data = self.coordinator.data
        return data[0] if data else None

    @property
    def native_temperature(self) -> float | None:
        """Observed temperature when available, else today's forecast maximum."""
        if (obs := self._obs) is not None and obs.temperature is not None:
            return obs.temperature
        try:
            return float(self._today["max_temp"])  # type: ignore[index]
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def humidity(self) -> float | None:
        """Observed relative humidity (MET observation access only)."""
        return obs.humidity if (obs := self._obs) is not None else None

    @property
    def native_wind_speed(self) -> float | None:
        """Observed wind speed in km/h (MET observation access only)."""
        return obs.wind_speed if (obs := self._obs) is not None else None

    @property
    def wind_bearing(self) -> float | str | None:
        """Observed wind direction (MET observation access only)."""
        return obs.wind_bearing if (obs := self._obs) is not None else None

    @property
    def native_visibility(self) -> float | None:
        """Observed visibility in km (MET observation access only)."""
        return obs.visibility if (obs := self._obs) is not None else None

    @property
    def condition(self) -> str | None:
        """Today's summary condition."""
        today = self._today
        return map_condition(today.get("summary_forecast")) if today else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Raw MET wording for today, useful in Malay dashboards."""
        today = self._today
        if not today:
            return None
        attributes: dict[str, Any] = {
            "summary_forecast": today.get("summary_forecast"),
            "summary_when": today.get("summary_when"),
            "morning_forecast": today.get("morning_forecast"),
            "afternoon_forecast": today.get("afternoon_forecast"),
            "night_forecast": today.get("night_forecast"),
            "min_temp": today.get("min_temp"),
        }
        if (met := self._met_data) is not None:
            if (met_today := met.day()) is not None:
                attributes.update(
                    {
                        "summary_en": met_today.get("FSIGW"),
                        "morning_forecast_en": met_today.get("FGM"),
                        "afternoon_forecast_en": met_today.get("FGA"),
                        "night_forecast_en": met_today.get("FGN"),
                    }
                )
            if met.state:
                attributes["state"] = met.state
            if met.latitude is not None and met.longitude is not None:
                attributes["latitude"] = met.latitude
                attributes["longitude"] = met.longitude
            if met.issued is not None:
                attributes["forecast_issued"] = met.issued.isoformat()
            if met.marine:
                attributes.update(met.marine)
        if (obs := self._obs) is not None:
            attributes["observation_station"] = obs.station_name or obs.station_id
            if obs.observed is not None:
                attributes["observation_time"] = obs.observed.isoformat()
            # HA weather has no current-precipitation property, so rain in
            # the last hour is an attribute (mm)
            if obs.precipitation is not None:
                attributes["precipitation_last_hour"] = obs.precipitation
            if obs.present_weather_id is not None:
                attributes["present_weather_id"] = obs.present_weather_id
        return attributes

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast."""
        forecasts: list[Forecast] = []
        for day in self.coordinator.data or []:
            try:
                date = datetime.strptime(day["date"], "%Y-%m-%d").replace(
                    tzinfo=dt_util.get_default_time_zone()
                )
                forecasts.append(
                    Forecast(
                        datetime=date.isoformat(),
                        native_temperature=float(day["max_temp"]),
                        native_templow=float(day["min_temp"]),
                        condition=map_condition(day.get("summary_forecast")),
                    )
                )
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.debug("Skipping malformed forecast day %s: %s", day, err)
        return forecasts
