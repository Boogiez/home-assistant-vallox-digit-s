# Changes

## 0.8.0b1

- Extract the RS485 implementation into an installable `vallox-digit-s` package.
- Add blocking and async clients, typed readings and a read-only CLI.
- Keep Home Assistant on the same protocol code and preserve existing entity IDs.
- Read the optional temperature request without enabling setting changes.
- Rewrite the public documentation and include the original Digit SE manual.

## 0.7.1b1

- Enforce the configured fan minimum across all Home Assistant controls.
- Fix setup cancellation cleanup and immediate control-state updates.
- Add tests against Home Assistant 2026.9.3 and 2026.10.4.
