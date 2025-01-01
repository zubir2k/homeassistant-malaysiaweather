"""Config flow for Malaysia Weather integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, FORECAST_URL, CONF_LOCATION_ID, CONF_LOCATION_NAME

_LOGGER = logging.getLogger(__name__)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Malaysia Weather."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Check if warnings are already configured
        if self._async_current_entries():
            return await self.async_step_location()

        # Create warnings entry first
        return self.async_create_entry(
            title="Warnings",
            data={},
        )

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding a weather location."""
        errors = {}

        if user_input is not None:
            try:
                # Check if location is already configured
                await self.async_set_unique_id(user_input[CONF_LOCATION_ID])
                self._abort_if_unique_id_configured()

                # Validate the location exists
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{FORECAST_URL}?contains={user_input[CONF_LOCATION_ID]}@location__location_id"
                    ) as response:
                        if response.status != 200:
                            raise InvalidLocation
                        data = await response.json()
                        if not data:
                            raise InvalidLocation
                        
                        # Get the location name from the API response
                        location_name = data[0]["location"]["location_name"].split(" (")[0]
                        
                return self.async_create_entry(
                    title=location_name,
                    data={
                        CONF_LOCATION_ID: user_input[CONF_LOCATION_ID],
                        CONF_LOCATION_NAME: location_name,
                    },
                )
            except InvalidLocation:
                errors["base"] = "invalid_location"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Get available locations from API
        locations = await self._async_get_locations()
        
        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema({
                vol.Required(CONF_LOCATION_ID): vol.In(locations),
            }),
            errors=errors,
        )

    @staticmethod
    async def _async_get_locations() -> dict[str, str]:
        """Get available locations from the API."""
        locations = {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(FORECAST_URL) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data:
                            location_id = item["location"]["location_id"]
                            location_name = item["location"]["location_name"].split(" (")[0]
                            locations[location_id] = location_name
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error fetching locations")
        
        return locations

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Malaysia Weather integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if not self.config_entry.data:  # This is the warnings entry
            return self.async_abort(reason="cannot_configure")

        errors = {}

        if user_input is not None:
            try:
                # Validate the location exists
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{FORECAST_URL}?contains={user_input[CONF_LOCATION_ID]}@location__location_id"
                    ) as response:
                        if response.status != 200:
                            raise InvalidLocation
                        data = await response.json()
                        if not data:
                            raise InvalidLocation
                        
                        # Get the location name from the API response
                        location_name = data[0]["location"]["location_name"].split(" (")[0]

                # Update the config entry with new location
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        **self.config_entry.data,
                        CONF_LOCATION_ID: user_input[CONF_LOCATION_ID],
                        CONF_LOCATION_NAME: location_name,
                    },
                )
                return self.async_create_entry(title="", data=user_input)

            except InvalidLocation:
                errors["base"] = "invalid_location"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Get available locations from API
        locations = await ConfigFlow._async_get_locations()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_LOCATION_ID,
                    default=self.config_entry.data.get(CONF_LOCATION_ID),
                ): vol.In(locations),
            }),
            errors=errors,
        )


class InvalidLocation(HomeAssistantError):
    """Error to indicate the location ID is invalid."""