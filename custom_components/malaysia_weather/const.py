"""Constants for Malaysia Weather integration."""
from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "malaysia_weather"

CONF_LOCATION_ID: Final = "location_id"
CONF_LOCATION_NAME: Final = "location_name"

# Optional MET Malaysia API key ("hybrid mode")
CONF_API_KEY: Final = "api_key"  # same string as homeassistant.const.CONF_API_KEY
CONF_MARINE_AREA: Final = "marine_area"
CONF_MARINE_AREA_NAME: Final = "marine_area_name"
CONF_MET_OBSERVATION: Final = "met_observation"  # capability flag from the probe
# Cached in entry.data so the MET location search runs only once per location
CONF_MET_LOCATION_ID: Final = "met_location_id"
CONF_MET_LOCATION_FOR: Final = "met_location_for"
CONF_MET_LATITUDE: Final = "met_latitude"
CONF_MET_LONGITUDE: Final = "met_longitude"
CONF_MET_STATION_ID: Final = "met_station_id"

# API URLs
FORECAST_URL: Final = "https://api.data.gov.my/weather/forecast"
WARNING_URL: Final = "https://api.data.gov.my/weather/warning"
EARTHQUAKE_URL: Final = "https://api.data.gov.my/weather/warning/earthquake"

# MET Malaysia API (optional key)
MET_API_URL: Final = "https://api.met.gov.my/v2.1"
MET_TIMEZONE: Final = "Asia/Kuala_Lumpur"
MET_PAGE_LIMIT: Final = 50
MET_FORECAST_DAYS: Final = 7
# data.gov.my id prefix -> MET location category searched first
MET_CATEGORY_BY_PREFIX: Final = {
    "Tn": "TOWN",
    "Ds": "DISTRICT",
    "Rc": "TOURISTDEST",
    "Dv": "DIVISION",
    "St": "STATE",
}
MET_LOCATION_CATEGORIES: Final = ("TOWN", "DISTRICT", "TOURISTDEST", "DIVISION", "STATE")
MET_OBSERVATION_TYPES: Final = (
    "TEMP",
    "RH",
    "WND_SPD",
    "WND_DIR",
    "VIS",
    "RAIN_1HR",
    "PRST_WX_ID",
)
# Consecutive MET failures before a repair issue is raised
MET_FAILURES_BEFORE_ISSUE: Final = 3
ISSUE_MET_API_KEY_INVALID: Final = "met_api_key_invalid"
ISSUE_MET_UNAVAILABLE: Final = "met_unavailable"

# Imagery: option label -> (translation key, url)
SATELLITE_URLS: Final = {
    "Satellite": "https://api.met.gov.my/static/images/satelit-latest.gif",
    "Radar": "https://api.met.gov.my/static/images/radar-latest.gif",
    "SWIRL": "https://api.met.gov.my/static/images/swirl-latest.gif",
    "Thunderstorm Warning": "https://www.met.gov.my/data/AmaranRibutPetir.jpg",
}

# Location Types
LOCATION_TYPES: Final = {
    "St": "State",
    "Rc": "Recreation Centre",
    "Ds": "District",
    "Tn": "Town",
    "Dv": "Division",
}

# Exact weather condition mapping (Malay text from MET -> HA condition)
CONDITION_MAPPING: Final = {
    "Berjerebu": "fog",
    "Tiada hujan": "sunny",
    "Berawan": "cloudy",
    "Mendung": "cloudy",
    "Hujan": "rainy",
    "Hujan di beberapa tempat": "rainy",
    "Hujan di satu dua tempat": "rainy",
    "Hujan di satu dua tempat di kawasan pantai": "rainy",
    "Hujan di satu dua tempat di kawasan pedalaman": "rainy",
    "Hujan lebat": "pouring",
    "Ribut petir": "lightning-rainy",
    "Ribut petir di beberapa tempat": "lightning-rainy",
    "Ribut petir di satu dua tempat": "lightning-rainy",
    "Ribut petir di satu dua tempat di kawasan pantai": "lightning-rainy",
    "Ribut petir di satu dua tempat di kawasan pedalaman": "lightning-rainy",
}

# Prefix fallbacks, used when MET publishes a phrase not listed above
CONDITION_PREFIX_MAPPING: Final = (
    ("ribut petir", "lightning-rainy"),
    ("hujan lebat", "pouring"),
    ("hujan", "rainy"),
    ("tiada hujan", "sunny"),
    ("berjerebu", "fog"),
    ("berawan", "cloudy"),
    ("mendung", "cloudy"),
)

ATTRIBUTION: Final = (
    "Weather forecast from Malaysia open data portal, delivered by "
    "Malaysian Meteorological Department (MET)"
)
ATTRIBUTION_MET: Final = (
    "Weather forecast from Malaysia open data portal and MET Malaysia API, "
    "delivered by Malaysian Meteorological Department (MET)"
)

MANUFACTURER: Final = "MET Malaysia"
CONFIGURATION_URL: Final = "https://www.met.gov.my"

# Update intervals
UPDATE_INTERVAL_FORECAST: Final = timedelta(hours=1)
UPDATE_INTERVAL_WARNINGS: Final = timedelta(minutes=5)
UPDATE_INTERVAL_IMAGERY: Final = timedelta(minutes=5)
# MET issues the forecast once a day; 3 hours is plenty and keeps calls low
UPDATE_INTERVAL_MET_FORECAST: Final = timedelta(hours=3)
UPDATE_INTERVAL_MET_OBSERVATION: Final = timedelta(minutes=30)
# Ignore observations older than this
MET_OBSERVATION_MAX_AGE: Final = timedelta(hours=3)

REQUEST_TIMEOUT: Final = 15


def map_condition(text: str | None) -> str | None:
    """Map a MET forecast phrase to a Home Assistant weather condition."""
    if not text:
        return None
    if text in CONDITION_MAPPING:
        return CONDITION_MAPPING[text]
    lowered = text.strip().lower()
    # "tiada hujan" must win over "hujan"
    if lowered.startswith("tiada hujan"):
        return "sunny"
    for prefix, condition in CONDITION_PREFIX_MAPPING:
        if lowered.startswith(prefix):
            return condition
    return None
