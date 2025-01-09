"""Image platform for Malaysia Weather integration."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SATELLITE_URLS

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Malaysia Weather image entities."""
    # Only set up image entities for the warnings entry (empty data)
    if entry.data:
        return

    entities = []
    for name, url in SATELLITE_URLS.items():
        entities.append(WeatherImageEntity(hass, name, url))
    
    async_add_entities(entities)

class WeatherImageEntity(ImageEntity):
    """Representation of a Weather Image entity."""

    def __init__(self, hass: HomeAssistant, name: str, url: str) -> None:
        """Initialize the image entity."""
        super().__init__(hass)
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_unique_id = f"malaysia_weather_{name.lower().replace(' ', '_')}"
        self._attr_image_url = url
        self._attr_content_type = "image/gif" if url.endswith(".gif") else "image/jpeg"
        self._attr_state = "OK"