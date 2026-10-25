# Vallox Digit S

Python client and Home Assistant integration for older Vallox / Ilmava Digit S
ventilation units with an LED wall panel. Uses the RS485 bus through a serial
adapter or transparent TCP bridge (9600 baud, 8N1).

The Python package works without Home Assistant. It provides blocking and async
clients, typed readings, fan control and supply-air temperature requests.

**Beta.** Tested on a legacy Digit S. This is a different protocol from the
Vallox MV WebSocket API; support for other models has not been established.

## Python

Requires Python 3.12 or later. Install from this repository:

```sh
pip install "git+https://github.com/Boogiez/home-assistant-vallox-digit-s.git"
```

```python
from vallox_digit_s import Client

with Client("socket://vallox-gateway.local:8899") as unit:
    status = unit.read()
    print(status.supply_temperature)  # °C; None if missing or stale
    print(status.fan_speed)           # device level
```

For asyncio, use `AsyncClient` with `async with` and `await unit.read()`.
The read-only CLI is `vallox-digit-s socket://vallox-gateway.local:8899`.

[API and examples](docs/api.md) · [Protocol and supported features](docs/feature-comparison.md)

## Home Assistant

Copy `custom_components/vallox_digit_s_legacy` into your configuration's
`custom_components` directory, restart, then add **Vallox Digit S** under
**Settings → Devices & services**. Requires Home Assistant 2026.9 or later.

The integration includes fan controls, temperature readings, a filter-change
record and optional airflow/power estimates using your own measurements.

[Home Assistant setup](docs/home-assistant.md) · [Suomeksi](README.fi.md)

## Scope

- Four air temperatures, actual fan level and temperature-request step.
- Confirmed fan changes at levels 5–8 and temperature-request steps 1–8.
- Passive bus capture for investigating other registers.

Heater enable, bypass and device fault codes are not verified for this controller.
They are not exposed as working features. Use one client per physical bus.

[Original Digit SE manual (PDF)](docs/manuals/D_se_kho.pdf) · [Tests](docs/validation.md)
· [Changes](CHANGELOG.md)

Code: GPL-3.0. [Credits and manual copyright](NOTICE.md).
