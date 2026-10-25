# Vallox Digit S → Home Assistant

A local Home Assistant integration for older **Vallox / Ilmava Digit S** units
with the LED wall panel. **This is a beta release.**

Read temperatures, adjust fan speed and the supply-air temperature request,
and track filter changes. Add your own airflow and power curves for estimates.

## Install

1. Download this project: **Code → Download ZIP**.
2. Copy `custom_components/vallox_digit_s_legacy` into Home Assistant's
   `config/custom_components/` folder, then restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → Vallox Digit S**.
4. Select your RS485 connection. For a transparent TCP bridge, use an address
   such as `socket://vallox-gateway.local:8899`.

Requires Home Assistant 2026.9 or later and a compatible RS485 bridge
(ESPHome or transparent TCP, 9600 baud / 8N1). Use only one integration per bus.

## Use

- Adjust the **Ilmanvaihto** fan entity. Supported fan levels are 5–8.
- Choose **Tuloilman lämpötilapyyntö** for the supply-air temperature request.
  Values marked **≈** are approximate LED-scale temperatures.
- Set the filter change date and service interval. Use the due sensor in a
  Home Assistant notification automation if desired.

Heater enable, bypass control and unverified device fault codes are not supported
in this release. Airflow and power figures are estimates, not meter readings.

[Suomenkielinen ohje](README.fi.md) · [Supported features](docs/feature-comparison.md)
· [Tests and limitations](docs/validation.md)

GPL-3.0. Credits and protocol sources: [NOTICE](NOTICE.md).
