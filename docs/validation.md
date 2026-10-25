# Validation and scope

## What is supported

The legacy Digit S temperature map is different from the newer Digit SE map.
The implemented wire writes remain limited to fan register `0x29` (levels 5–8)
and temperature-request register `0xA4` (eight LED-panel steps). They use a
fresh mainboard read before a change and mainboard readback afterwards.
There are no automatic write retries or setting writes during startup.

The project reads four temperatures, the actual fan level and the temperature
request. It provides standard fan/select/number entities, a local filter service
log, connection diagnostics and bounded passive bus capture. Airflow, power and
heat-transfer figures require a user-supplied profile and are estimates.

## Audit changes in 0.7.1b1

- Enforce the configured fan minimum at the shared coordinator boundary, including
  number services and automations. The number entity now displays that minimum.
- Clean up the reader when the initial refresh fails or setup is cancelled.
- Pass the config entry explicitly to the Home Assistant coordinator API.
- Publish control readbacks after releasing the transport lock, so sibling
  controls remain available immediately after a command completes or fails.
- Correct public documentation, project URLs, attribution and test-file encoding.

## Evidence

- The 0.7.0rc1 baseline has run on one old LED-panel Digit S. Read-only live
  inspection confirmed fresh measurements and coherent control readbacks during
  this audit. Earlier physical tests verified fan 6 → 5 → 6 and temperature
  step 4 → 5 → 4, including return to the original settings.
- Offline protocol and API-double tests cover packet validation, all byte values,
  noise, fragmented traffic, echoes, stale values, timeouts, locks, cooldown,
  cancellation, capture, maintenance and calculation boundaries.
- A local TCP simulator also exercises the actual serialx transport, reading,
  confirmed fan commands and capture with zero transmitted bytes.
- GitHub Actions runs the offline suite on Python 3.12 and 3.14, plus actual
  Home Assistant 2026.9.3 and 2026.10.4 setup, entity, service, options and unload
  tests. Only the hardware reader and USB discovery scan are simulated in the
  Home Assistant tests; those tests cannot establish physical device behavior.

The audit does not claim exhaustive hardware verification on every Digit S.
The 0.7.1b1 application-side changes are tested separately from the installed
0.7.0rc1 baseline; publishing the source does not update an existing installation.

## Known limitations

- The hardware-confirmed temperature anchors are 10, 20 and 27 °C. The other
  LED steps have approximate Celsius labels, explicitly marked `≈`.
- Fan percentage is a position among allowed levels, not measured airflow or power.
  Shutdown and levels below 5 are intentionally not offered by this profile.
- Heater enable/activity, bypass, device fault codes, firmware service timers,
  optional CO2/RH sensors and protection/calibration settings are not verified
  for this old controller and are not exposed as working controls or sensors.
- A filter reminder is a Home Assistant maintenance record. It does not reset
  the physical panel's service light. Notification delivery is a user automation.
- Supply-air warming may include the electric heater. Temperature ratios must
  not be presented as seasonal heat-recovery efficiency or heater electricity use.
- Generic automatic boost/home-sensor control is not bundled. Existing household
  automations can use the normal entities and should handle unavailable states.
- Use only one client on a physical RS485 bus. Register mapping and command
  limits should be checked before use on a different unit.

## Run the tests

```sh
python -m pip install -r requirements-test.txt
python -m pytest tests -q
```

The separate Linux Home Assistant runtime jobs are defined in
`.github/workflows/tests.yml`; they require Python 3.14.2 or later.
