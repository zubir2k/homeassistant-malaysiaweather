"""Diagnostics for Malaysia Weather."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_MET_LATITUDE, CONF_MET_LONGITUDE
from .coordinator import (
    LocationRuntimeData,
    MalaysiaWeatherConfigEntry,
    WarningsRuntimeData,
)

TO_REDACT = {
    CONF_API_KEY,
    CONF_MET_LATITUDE,
    CONF_MET_LONGITUDE,
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MalaysiaWeatherConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, with the MET key redacted."""
    diagnostics: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
    }
    runtime = getattr(entry, "runtime_data", None)
    if isinstance(runtime, LocationRuntimeData):
        diagnostics["forecast"] = {
            "last_update_success": runtime.forecast.last_update_success,
            "days": len(runtime.forecast.data or []),
        }
        diagnostics["met_mode"] = (
            "observation" if runtime.observation else "key" if runtime.met else "basic"
        )
        for name in ("met", "observation"):
            coordinator = getattr(runtime, name)
            if coordinator is None:
                continue
            data = coordinator.data
            diagnostics[name] = {
                "last_update_success": coordinator.last_update_success,
                "data": async_redact_data(asdict(data), TO_REDACT) if data else None,
            }
    elif isinstance(runtime, WarningsRuntimeData):
        diagnostics["warnings"] = {
            "last_update_success": runtime.warnings.last_update_success,
            "count": len(runtime.warnings.data or []),
        }
        diagnostics["earthquake"] = {
            "last_update_success": runtime.earthquake.last_update_success,
            "count": len(runtime.earthquake.data or []),
        }
        diagnostics["imagery"] = {
            key: coord.last_update_success for key, coord in runtime.imagery.items()
        }
    return diagnostics
