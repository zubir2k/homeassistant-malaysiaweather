"""Select platform for Malaysia Weather integration."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SATELLITE_URLS
from .coordinator import MalaysiaWeatherConfigEntry, WarningsRuntimeData
from .entity import warnings_device_info

STORAGE_KEY = f"{DOMAIN}.satellite_selection"
STORAGE_VERSION = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MalaysiaWeatherConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the imagery selector."""
    if not isinstance(entry.runtime_data, WarningsRuntimeData):
        return

    store: Store[dict[str, str]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored = await store.async_load()
    initial = "Satellite"
    if stored and stored.get("option") in SATELLITE_URLS:
        initial = stored["option"]

    async_add_entities([SatelliteImagerySelect(store, initial, entry)])


class SatelliteImagerySelect(SelectEntity):
    """Pick which MET image the `url` attribute points to."""

    _attr_has_entity_name = True
    _attr_translation_key = "satellite_imagery"
    _attr_options = list(SATELLITE_URLS)
    _attr_unique_id = "malaysia_satellite_imagery"  # unchanged from v1.0.x

    def __init__(self, store: Store[dict[str, str]], initial: str, entry: MalaysiaWeatherConfigEntry) -> None:
        """Initialize the select entity."""
        self._store = store
        self._attr_current_option = initial
        self._attr_device_info = warnings_device_info(entry)

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose the URL of the selected image."""
        return {"url": SATELLITE_URLS.get(self._attr_current_option or "")}

    async def async_select_option(self, option: str) -> None:
        """Change the selected image."""
        self._attr_current_option = option
        await self._store.async_save({"option": option})
        self.async_write_ha_state()
