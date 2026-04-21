"""Select platform for Malaysia Weather integration."""
from __future__ import annotations

import logging
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SATELLITE_URLS

_LOGGER = logging.getLogger(__name__)
STORAGE_KEY = f"{DOMAIN}.satellite_selection"
STORAGE_VERSION = 1

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Malaysia Weather select entities."""
    if entry.data:
        return

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored = await store.async_load()

    initial_option = "Satellite"
    if stored and stored.get("option") in list(SATELLITE_URLS.keys()):
        initial_option = stored["option"]

    async_add_entities([SatelliteImagerySelect(store, initial_option)])

class SatelliteImagerySelect(SelectEntity, RestoreEntity):
    """Representation of a Satellite Imagery select entity."""

    _attr_has_entity_name = True
    _attr_name = "Satellite Imagery"
    _attr_options = list(SATELLITE_URLS.keys())

    def __init__(self, store: Store, initial_option: str) -> None:
        """Initialize the select entity."""
        self._attr_unique_id = "malaysia_satellite_imagery"
        self._attr_current_option = initial_option  
        self._store = store

    async def async_added_to_hass(self) -> None:
        """Nothing to restore — already loaded before entity was created."""
        await super().async_added_to_hass()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        """Return the attributes for the select entity."""
        return {"url": SATELLITE_URLS.get(self._attr_current_option)}

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        if option in self._attr_options:
            self._attr_current_option = option
            await self._store.async_save({"option": option})
            self.async_write_ha_state()
