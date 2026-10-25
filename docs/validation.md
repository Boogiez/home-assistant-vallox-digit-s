# Testing

The test suite covers packet framing, NTC conversion, invalid values, partial
traffic, echoes, stale readings, timeouts, write whitelists, cooldowns, cancellation
and passive capture. A local TCP simulator exercises the real serialx transport.

The standalone-client tests cover blocking and async use, status expiry,
read-only operation, command readback and cancellation. Packaging checks install
the wheel and import it in a separate process without Home Assistant.

GitHub Actions runs Python 3.12 and 3.14, plus integration tests against actual
Home Assistant 2026.9.3 and 2026.10.4. Hardware I/O is simulated in those runtime
tests; setup, entities, services, options and unload use Home Assistant itself.

```sh
pip install . -r requirements-test.txt
python -m pytest tests -q
```

Real-unit checks have verified temperatures, fan changes 6 → 5 → 6 and
temperature-request steps 4 → 5 → 4 on one legacy Digit S. That does not establish
compatibility with every controller. The standalone-client refactor is tested
offline; it has not been installed or physically tested as a new version.

The wire implementation is shared with the Home Assistant integration. Changes
to its packet whitelist or register map need separate device validation.
