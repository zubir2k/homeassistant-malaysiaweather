"""Image platform for Malaysia Weather integration."""
from __future__ import annotations
import asyncio
from datetime import timedelta
import logging
import aiohttp

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN, SATELLITE_URLS

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Malaysia Weather image entities."""
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
        self._cached_image: bytes | None = None
        self._last_etag: str | None = None

    async def async_added_to_hass(self) -> None:
        """Start polling when entity is added."""
        await super().async_added_to_hass()
        await self._fetch_image()
        # Schedule periodic polling
        self._unsub = async_track_time_interval(
            self.hass, self._handle_interval, SCAN_INTERVAL
        )

    async def async_will_remove_from_hass(self) -> None:
        """Stop polling when entity is removed."""
        if hasattr(self, "_unsub"):
            self._unsub()

    async def _handle_interval(self, now) -> None:
        """Called on each poll interval."""
        await self._fetch_image()

    async def _fetch_image(self) -> None:
        """Fetch the image and update state if it has changed."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._attr_image_url) as response:
                    if response.status != 200:
                        return

                    new_etag = response.headers.get("ETag") or response.headers.get("Last-Modified")
                    new_image = await response.read()

                    changed = False
                    if new_etag:
                        if new_etag != self._last_etag:
                            changed = True
                            self._last_etag = new_etag
                    elif new_image != self._cached_image:
                        changed = True

                    if changed or self._cached_image is None:
                        self._cached_image = new_image
                        self._attr_image_last_updated = dt_util.utcnow()
                        self.async_write_ha_state()
                        _LOGGER.debug("Image updated for %s", self._attr_name)

        except Exception as err:
            _LOGGER.error("Error fetching image for %s: %s", self._attr_name, err)

    async def async_image(self) -> bytes | None:
        """Return the cached image bytes."""
        return self._cached_image
