![github](https://github.com/user-attachments/assets/9b891ff7-7079-460d-afd3-97c5615f6110) \
[![hacs_badge](https://img.shields.io/badge/HACS-Integration-41BDF5.svg)](https://github.com/hacs/integration)
![GitHub all releases](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=Download%20Count&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.malaysia_weather.total)
[![Buy](https://img.shields.io/badge/Belanja-Coffee-yellow.svg)](https://zubirco.de/buymecoffee)
[![GitHub Release](https://img.shields.io/github/release/zubir2k/homeassistant-malaysiaweather.svg)](https://github.com/zubir2k/homeassistant-malaysiaweather/releases/)

## Features
- Multiple Location supported
- Earthquake sensor
- Warning sensor

> [!Tip]
> This integration provides ONLY weekly data (7 days) at the moment

![image](https://github.com/user-attachments/assets/b712ea13-ebc3-4813-b6b8-1e1049e7165e)

## Installation
#### With HACS
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zubir2k&repository=homeassistant-malaysiaweather&category=integration)

> [!Tip]
> If you are unable to use the button above, manually search for Malaysia Weather in HACS.

#### Manual
1. Copy the `malaysia_weather` directory from `custom_components` in this repository and place inside your Home Assistant's `custom_components` directory.
2. Restart Home Assistant
3. Follow the instructions in the `Setup` section

> [!WARNING]
> If installing manually, in order to be alerted about new releases, you will need to subscribe to releases from this repository.

## Setup
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=malaysia_weather)

> [!Tip]
> If you are unable to use the button above, follow the steps below:
> 1. Navigate to the Home Assistant Integrations page (Settings --> Devices & Services).
> 2. Click the `+ ADD INTEGRATION` button in the lower right-hand corner.
> 3. Search for `Malaysia Weather`.
> 4. The integration will create `Earthquake` and `Warning` sensors.
> 5. Next, continue by clicking the `Add Service` button.
> 6. Select the location that you wish add (location are sorted alphabetically).
> 7. Weather sensor will be created based on the location that you have chosen.
> 8. You may also continue adding another location by clicking the `Add Service` button.

![image](https://github.com/user-attachments/assets/203852af-094c-45a5-9f77-151a31d42969)

## Main Contributors
- [Dr. Yusri Salleh](https://github.com/kucau0901)
- [Zubir Jamal](https://github.com/zubir2k)

## Credits
![logo](https://github.com/user-attachments/assets/eb467f55-6cb9-4420-ab5e-7bdd3b28be9c) Data provided by MET Malaysia via [data.gov.my](https://data.gov.my/)
