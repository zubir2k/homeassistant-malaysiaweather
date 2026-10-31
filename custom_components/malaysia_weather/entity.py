"""Shared device info for Malaysia Weather entities."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import CONF_LOCATION_NAME, CONFIGURATION_URL, DOMAIN, MANUFACTURER


def location_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Device for a forecast location; its name is the location name."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_LOCATION_NAME, entry.title),
        manufacturer=MANUFACTURER,
        model="Location forecast",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=CONFIGURATION_URL,
    )


def warnings_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Device for the nationwide warnings and imagery."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=MANUFACTURER,
        manufacturer=MANUFACTURER,
        model="Warnings & Imagery",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=CONFIGURATION_URL,
    )
