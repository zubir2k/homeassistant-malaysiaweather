"""Image platform for Malaysia Weather integration."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import ImageryCoordinator, MalaysiaWeatherConfigEntry, WarningsRuntimeData
from .entity import warnings_device_info

PARALLEL_UPDATES = 0

TRANSLATION_KEYS = {
    "Satellite": "satellite",
    "Radar": "radar",
    "SWIRL": "swirl",
    "Thunderstorm Warning": "thunderstorm_warning",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MalaysiaWeatherConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the MET imagery entities."""
    runtime = entry.runtime_data
    if not isinstance(runtime, WarningsRuntimeData):
        return
    async_add_entities(
        WeatherImageEntity(hass, coordinator, name, entry)
        for name, coordinator in runtime.imagery.items()
    )


class WeatherImageEntity(CoordinatorEntity[ImageryCoordinator], ImageEntity):
    """One MET imagery feed (satellite, radar, SWIRL, thunderstorm)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ImageryCoordinator,
        name: str,
        entry: MalaysiaWeatherConfigEntry,
    ) -> None:
        """Initialize the image entity."""
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_translation_key = TRANSLATION_KEYS[name]
        # Unchanged from v1.0.x so existing entity IDs are kept
        self._attr_unique_id = f"malaysia_weather_{name.lower().replace(' ', '_')}"
        self._attr_content_type = (
            "image/gif" if coordinator.url.endswith(".gif") else "image/jpeg"
        )
        self._attr_device_info = warnings_device_info(entry)
        self._fingerprint: str | None = None
        self._update_from_coordinator()

    @callback
    def _update_from_coordinator(self) -> None:
        data = self.coordinator.data
        if data and data.fingerprint != self._fingerprint:
            self._fingerprint = data.fingerprint
            self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Bump the timestamp only when the picture changed."""
        self._update_from_coordinator()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return the latest image bytes."""
        data = self.coordinator.data
        return data.content if data else None
