"""Sensor platform for Malaysia Weather integration."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION
from .coordinator import (
    MalaysiaWeatherConfigEntry,
    MalaysiaWeatherCoordinator,
    WarningsRuntimeData,
)
from .entity import warnings_device_info

PARALLEL_UPDATES = 0


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MalaysiaWeatherConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up warning sensors for the Warnings & Imagery entry."""
    runtime = entry.runtime_data
    if not isinstance(runtime, WarningsRuntimeData):
        return
    async_add_entities(
        [
            WeatherWarningSensor(runtime.warnings, entry),
            EarthquakeWarningSensor(runtime.earthquake, entry),
        ]
    )


class _WarningsSensor(CoordinatorEntity[MalaysiaWeatherCoordinator], SensorEntity):
    """Base for the nationwide warning sensors."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: MalaysiaWeatherCoordinator, entry: MalaysiaWeatherConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = warnings_device_info(entry)

    @property
    def _latest(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        return data[0] if data else None


class WeatherWarningSensor(_WarningsSensor):
    """Latest MET weather warning."""

    _attr_translation_key = "weather_warning"
    _attr_unique_id = "malaysia_weather_warning"  # unchanged from v1.0.x

    @property
    def native_value(self) -> str | None:
        latest = self._latest
        heading = latest.get("heading_en") if latest else None
        return heading[:255] if heading else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        latest = self._latest
        if not latest:
            return {}
        return {
            "valid_from": latest.get("valid_from"),
            "valid_to": latest.get("valid_to"),
            "text": latest.get("text_en"),
            "instruction": latest.get("instruction_en"),
            "heading_bm": latest.get("heading_bm"),
            "text_bm": latest.get("text_bm"),
        }


class EarthquakeWarningSensor(_WarningsSensor):
    """Latest MET earthquake report."""

    _attr_translation_key = "earthquake_warning"
    _attr_unique_id = "malaysia_earthquake_warning"  # unchanged from v1.0.x

    @property
    def native_value(self) -> str | None:
        latest = self._latest
        return latest.get("status") if latest else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        latest = self._latest
        if not latest:
            return {}
        return {
            "magnitude": _to_float(latest.get("magdefault")),
            "depth": _to_float(latest.get("depth")),
            "location": latest.get("location_original"),
            "distance_from_malaysia": latest.get("n_distancemas"),
            "datetime": latest.get("localdatetime"),
        }
