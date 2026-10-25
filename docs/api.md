# Python API

`Client` is blocking; `AsyncClient` runs the same implementation in worker threads.
Neither constructor opens a connection. Each read, command or capture opens its
own transport and closes it when finished. Closing a client is permanent.

## Reading

```python
import asyncio
from vallox_digit_s import AsyncClient, ConnectionState

async def main():
    async with AsyncClient("socket://vallox-gateway.local:8899") as unit:
        status = await unit.read()
        if status.state == ConnectionState.READY:
            print(status.supply_temperature)
        else:
            print(status.state, status.errors)

asyncio.run(main())
```

`read()` polls the unit. `status` returns cached readings with current sample ages,
without sending anything. There is no background polling; a 60-second polling
interval matches the Home Assistant integration.

| Status field | Value |
|---|---|
| `state` | `ready`, `partial`, `unavailable`, `listening` or `closed` |
| `outdoor_temperature`, `supply_temperature`, `extract_temperature`, `exhaust_temperature` | °C, or `None` |
| `fan_speed` | Device level 1–8, or `None`; writing is limited to 5–8 |
| `temperature_step` | Supply-air request step 1–8, or `None` |
| `samples` | Immutable readings with raw byte, timestamp and age |
| `errors` | `(register_or_transport, error_code)` tuples from the last poll |

Readings expire after 180 seconds. A `ready` status requires all five core
readings (four temperatures and fan speed), with no core poll errors. The
temperature request is optional and can be missing even when the state is ready.
`status.to_dict()` returns a detached JSON-compatible copy. Connection failures
are reported in the status; a partial reply does not discard other fresh values.

## Commands

```python
from vallox_digit_s import Client, ControlError

with Client("socket://vallox-gateway.local:8899", allow_control=True) as unit:
    unit.read()
    try:
        actual = unit.set_fan_speed(6)
        print(actual.fan_speed)
    except ControlError as error:
        print(error)
```

`set_fan_speed(level)` accepts integers 5–8. `set_temperature_step(step)` accepts
integers 1–8. Async clients expose the same methods with `await`.
Commands require `allow_control=True`, a fresh cached reading, a fresh mainboard
query and a successful readback. Consecutive commands share a three-second
cooldown. There are no automatic write retries or startup setting changes.

Invalid values raise `ValueError`. Refused or unconfirmed commands raise
`ControlError`; a command may already have reached the unit, so read its state
before retrying. The library does not enforce a building-specific ventilation
minimum; callers must apply any higher installation limit themselves.

The temperature setting is an eight-step LED scale, not a continuous calibrated
Celsius setpoint. Confirmed scale anchors are step 1 = 10 °C, 5 = 20 °C and
8 = 27 °C. Setting it does not enable the heater or set its power.

## Capture and shutdown

`capture(seconds=120)` listens for 1–300 seconds and transmits no bytes. It returns
the `passive_capture` diagnostic record, including frames and UTC timestamps.
`cancel_capture()` ends capture without closing the client. Diagnostic status
strings retain the legacy integration's Finnish wording; `Status.state` is the
application-facing language-independent state.

Use the context managers, or call `close()` / `await aclose()`. Cancelling an
active async operation stops the client and waits for its worker to release the
transport before propagating cancellation. Create a new client to reconnect.
Cancelling a queued operation does not interrupt another active operation.

`diagnostics()` returns a detached snapshot with bounded frame buffers. It omits
the connection address. Only one program should own a physical RS485 bus;
application locks cannot coordinate separate processes.

## Development

```sh
pip install . -r requirements-test.txt build
python -m pytest tests -q
python -m build
```

The installable `vallox_digit_s` package lives inside the custom component so
Home Assistant ships exactly the same protocol code. The wheel contains only
that package, not Home Assistant. Modules at the custom-component root retain
compatibility imports for existing integration code.
