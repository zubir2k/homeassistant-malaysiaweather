"""Config flow for Malaysia Weather integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_API_KEY,
    CONF_LOCATION_ID,
    CONF_LOCATION_NAME,
    CONF_MARINE_AREA,
    CONF_MARINE_AREA_NAME,
    CONF_MET_LATITUDE,
    CONF_MET_LOCATION_FOR,
    CONF_MET_LOCATION_ID,
    CONF_MET_LONGITUDE,
    CONF_MET_OBSERVATION,
    CONF_MET_STATION_ID,
    DOMAIN,
    FORECAST_URL,
)
from .coordinator import async_clear_met_issues, async_fetch_json
from .met import MetAuthError, MetClient, MetError, distance_km

_LOGGER = logging.getLogger(__name__)

WARNINGS_UNIQUE_ID = "warnings"


def _clean_name(raw: str) -> str:
    return raw.split(" (")[0].strip()


async def _async_get_locations(hass: HomeAssistant) -> dict[str, str]:
    """Return {location_id: name}, one id per name, sorted by name."""
    data = await async_fetch_json(hass, FORECAST_URL)
    locations: dict[str, str] = {}
    seen: set[str] = set()
    for item in data:
        location = item.get("location") or {}
        location_id = location.get("location_id")
        name = location.get("location_name")
        if not location_id or not name:
            continue
        name = _clean_name(name)
        if name in seen:
            continue
        seen.add(name)
        locations[location_id] = name
    return dict(sorted(locations.items(), key=lambda kv: kv[1]))


NO_MARINE_AREA = "none"
MET_CACHED_DATA = (
    CONF_MET_LOCATION_ID,
    CONF_MET_LOCATION_FOR,
    CONF_MET_LATITUDE,
    CONF_MET_LONGITUDE,
    CONF_MET_STATION_ID,
)

_API_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _location_schema(
    locations: dict[str, str], default: str | None = None, api_key: str | None = None
) -> vol.Schema:
    selector = SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=k, label=v) for k, v in locations.items()],
            mode=SelectSelectorMode.DROPDOWN,
            sort=False,
        )
    )
    key = (
        vol.Required(CONF_LOCATION_ID, default=default)
        if default
        else vol.Required(CONF_LOCATION_ID)
    )
    # Optional, masked; a suggested value (not a default) lets the user clear it
    api_key_field = vol.Optional(
        CONF_API_KEY, description={"suggested_value": api_key} if api_key else None
    )
    return vol.Schema({key: selector, api_key_field: _API_KEY_SELECTOR})


async def async_validate_api_key(hass: HomeAssistant, api_key: str) -> bool:
    """Check a MET key; return True when it also has observation access.

    Raises MetAuthError (401) or MetError (timeout/connection/other).
    """
    client = MetClient(hass, api_key)
    await client.async_validate()
    return await client.async_probe_observation()


async def _async_check_key(
    hass: HomeAssistant, user_input: dict[str, Any], errors: dict[str, str]
) -> tuple[str, bool]:
    """Validate the optional key in a form; fills errors on failure."""
    api_key = (user_input.get(CONF_API_KEY) or "").strip()
    if not api_key:
        return "", False
    try:
        return api_key, await async_validate_api_key(hass, api_key)
    except MetAuthError:
        errors[CONF_API_KEY] = "invalid_api_key"
    except MetError as err:
        _LOGGER.debug("Could not validate MET API key: %s", err)
        errors["base"] = "cannot_connect"
    return api_key, False


def _key_options(api_key: str, observation: bool) -> dict[str, Any]:
    return {CONF_API_KEY: api_key, CONF_MET_OBSERVATION: observation} if api_key else {}


class MalaysiaWeatherConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Malaysia Weather."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._locations: dict[str, str] = {}

    def _has_warnings_entry(self) -> bool:
        return any(
            CONF_LOCATION_ID not in entry.data for entry in self._async_current_entries()
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First run creates Warnings & Imagery; later runs add a location."""
        if self._has_warnings_entry():
            return await self.async_step_location()

        await self.async_set_unique_id(WARNINGS_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Warnings & Imagery", data={})

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a forecast location."""
        errors: dict[str, str] = {}

        if not self._locations:
            try:
                self._locations = await _async_get_locations(self.hass)
            except UpdateFailed:
                _LOGGER.exception("Error fetching locations")
                return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            location_id = user_input[CONF_LOCATION_ID]
            if location_id not in self._locations:
                errors["base"] = "invalid_location"
            else:
                await self.async_set_unique_id(location_id)
                self._abort_if_unique_id_configured()
                api_key, observation = await _async_check_key(self.hass, user_input, errors)
                if not errors:
                    name = self._locations[location_id]
                    return self.async_create_entry(
                        title=name,
                        data={CONF_LOCATION_ID: location_id, CONF_LOCATION_NAME: name},
                        options=_key_options(api_key, observation),
                    )

        return self.async_show_form(
            step_id="location",
            data_schema=self.add_suggested_values_to_schema(
                _location_schema(self._locations), user_input or {}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return MalaysiaWeatherOptionsFlow()


class MalaysiaWeatherOptionsFlow(OptionsFlow):
    """Change the location, the optional MET key and the marine area.

    `self.config_entry` is provided by Home Assistant (2024.11+); setting it
    in __init__ crashes on 2025.12 and newer.
    """

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._new_data: dict[str, Any] = {}
        self._new_options: dict[str, Any] = {}
        self._waters: dict[str, str] = {}
        self._nearest: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Location and optional MET API key."""
        entry = self.config_entry
        if CONF_LOCATION_ID not in entry.data:
            return self.async_abort(reason="cannot_configure")

        errors: dict[str, str] = {}
        try:
            locations = await _async_get_locations(self.hass)
        except UpdateFailed:
            _LOGGER.exception("Error fetching locations")
            return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            location_id = user_input[CONF_LOCATION_ID]
            if location_id not in locations:
                errors["base"] = "invalid_location"
            elif location_id != entry.unique_id and any(
                other.unique_id == location_id
                for other in self.hass.config_entries.async_entries(DOMAIN)
            ):
                errors["base"] = "location_already_configured"
            else:
                api_key, observation = await _async_check_key(self.hass, user_input, errors)
                if not errors:
                    name = locations[location_id]
                    data = {**entry.data, CONF_LOCATION_ID: location_id, CONF_LOCATION_NAME: name}
                    if location_id != entry.data.get(CONF_LOCATION_ID):
                        # New place: search MET again and find a new station
                        for key in MET_CACHED_DATA:
                            data.pop(key, None)
                    self._new_data = data
                    self._new_options = _key_options(api_key, observation)
                    if api_key:
                        return await self.async_step_marine()
                    return self._async_save()

        current_key = entry.options.get(CONF_API_KEY)
        return self.async_show_form(
            step_id="init",
            data_schema=_location_schema(
                locations,
                (user_input or {}).get(CONF_LOCATION_ID) or entry.data.get(CONF_LOCATION_ID),
                current_key,
            ),
            errors=errors,
        )

    async def async_step_marine(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optional marine area (MET WATERS) for wind and wave attributes."""
        if not self._waters:
            try:
                client = MetClient(self.hass, self._new_options[CONF_API_KEY])
                waters = await client.async_locations("WATERS")
            except MetError as err:
                _LOGGER.debug("Could not load MET marine areas: %s", err)
                waters = []
            self._waters = {
                item["id"]: str(item.get("name") or item["id"]).title()
                for item in waters
                if item.get("id")
            }
            self._nearest = _nearest_waters(waters, self._new_data)
        if not self._waters:
            # Marine is optional; never block saving the key on it
            return self._async_save()

        if user_input is not None:
            area = user_input.get(CONF_MARINE_AREA) or NO_MARINE_AREA
            if area in self._waters:
                self._new_options[CONF_MARINE_AREA] = area
                self._new_options[CONF_MARINE_AREA_NAME] = self._waters[area]
            return self._async_save()

        current = self.config_entry.options.get(CONF_MARINE_AREA)
        default = current if current in self._waters else (self._nearest or NO_MARINE_AREA)
        options = [SelectOptionDict(value=NO_MARINE_AREA, label="—")] + [
            SelectOptionDict(value=k, label=v)
            for k, v in sorted(self._waters.items(), key=lambda kv: kv[1])
        ]
        return self.async_show_form(
            step_id="marine",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_MARINE_AREA, default=default): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN, sort=False
                        )
                    )
                }
            ),
        )

    @callback
    def _async_save(self) -> ConfigFlowResult:
        """Store the change and reload the entry."""
        entry = self.config_entry
        self.hass.config_entries.async_update_entry(
            entry,
            title=self._new_data[CONF_LOCATION_NAME],
            unique_id=self._new_data[CONF_LOCATION_ID],
            data=self._new_data,
            options=self._new_options,
        )
        if not self._new_options.get(CONF_API_KEY):
            # Basic mode: nothing left to repair
            async_clear_met_issues(self.hass, entry)
        # Reload so the coordinators use the new location and key right away
        self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_create_entry(data=self._new_options)


def _nearest_waters(waters: list[dict[str, Any]], data: dict[str, Any]) -> str | None:
    """Nearest WATERS area, only when MET gives both sides coordinates."""
    lat, lon = data.get(CONF_MET_LATITUDE), data.get(CONF_MET_LONGITUDE)
    if lat is None or lon is None:
        return None
    best: tuple[float, str] | None = None
    for item in waters:
        try:
            w_lat, w_lon = float(item["latitude"]), float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        dist = distance_km(float(lat), float(lon), w_lat, w_lon)
        if best is None or dist < best[0]:
            best = (dist, item["id"])
    return best[1] if best else None
