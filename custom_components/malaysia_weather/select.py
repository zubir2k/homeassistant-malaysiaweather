"""Select platform for Malaysia Weather integration."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SATELLITE_URLS

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Malaysia Weather select entities."""
    # Only set up select entities for the warnings entry (empty data)
    if entry.data:
        return

    async_add_entities([SatelliteImagerySelect()])

class SatelliteImagerySelect(SelectEntity):
    """Representation of a Satellite Imagery select entity."""

    _attr_has_entity_name = True
    _attr_name = "Satellite Imagery"
    _attr_options = list(SATELLITE_URLS.keys())

    def __init__(self) -> None:
        """Initialize the select entity."""
        self._attr_unique_id = "malaysia_satellite_imagery"
        self._attr_current_option = "Satellite"

    @property
    def extra_state_attributes(self):
        """Return the attributes for the select entity."""
        return {"url": SATELLITE_URLS.get(self._attr_current_option)}

    async def async_select_option(self, option: str) -> None:
        """Update the selected option."""
        if option in self._attr_options:
            self._attr_current_option = option
            self.async_write_ha_state()
