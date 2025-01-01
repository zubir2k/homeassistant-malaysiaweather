"""Constants for Malaysia Weather integration."""
from typing import Final

DOMAIN: Final = "malaysia_weather"

CONF_LOCATION_ID: Final = "location_id"
CONF_LOCATION_NAME: Final = "location_name"

# API URLs
FORECAST_URL: Final = "https://api.data.gov.my/weather/forecast"
WARNING_URL: Final = "https://api.data.gov.my/weather/warning"
EARTHQUAKE_URL: Final = "https://api.data.gov.my/weather/warning/earthquake"

# Default icon
DEFAULT_ICON = "mdi:weather-partly-cloudy"

# Location Types
LOCATION_TYPES = {
    "St": "State",
    "Rc": "Recreation Centre",
    "Ds": "District",
    "Tn": "Town",
    "Dv": "Division"
}

# Weather condition mapping
CONDITION_MAPPING = {
    "Berjerebu": "fog",
    "Tiada hujan": "sunny",
    "Hujan": "rainy",
    "Hujan di beberapa tempat": "rainy",
    "Hujan di satu dua tempat": "rainy",
    "Hujan di satu dua tempat di kawasan pantai": "rainy",
    "Hujan di satu dua tempat di kawasan pedalaman": "rainy",
    "Ribut petir": "lightning-rainy",
    "Ribut petir di beberapa tempat": "lightning-rainy",
    "Ribut petir di satu dua tempat": "lightning-rainy",
    "Ribut petir di satu dua tempat di kawasan pantai": "lightning-rainy",
    "Ribut petir di satu dua tempat di kawasan pedalaman": "lightning-rainy",
}

# Attribution
ATTRIBUTION: Final = "Weather forecast from Malaysia open data portal, delivered by Malaysian Meteorological Department (MET)"

# Update intervals (in seconds)
UPDATE_INTERVAL_FORECAST: Final = 3600  # 1 hour, since forecast updates daily
UPDATE_INTERVAL_WARNINGS: Final = 300   # 5 minutes, since warnings update when required