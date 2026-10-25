# Home Assistant

Requires Home Assistant 2026.9 or later. Copy the entire
`custom_components/vallox_digit_s_legacy` directory into your configuration's
`custom_components` directory, restart, then add **Vallox Digit S** under
**Settings → Devices & services**.

The nested `vallox_digit_s` directory is required. It contains the same protocol
implementation as the standalone Python package. You do not need to install the
Python package separately inside Home Assistant.

## Connection

Use a transparent TCP bridge (`socket://host:port`), a local `/dev/…` serial port,
or an ESPHome serial connection offered by Home Assistant. Set the RS485 side to
9600 baud, 8 data bits, no parity and one stop bit. Use one connection per bus.

## Controls and readings

- **Ilmanvaihto**: fan control. Percentage selects a supported level; it is not
  a measured percentage of airflow or electrical power.
- **Tuloilman lämpötilapyyntö**: the controller's eight-step temperature request.
  Intermediate Celsius labels marked ≈ are approximate.
- Filter date and interval: local maintenance records, with a due-date sensor.
  They do not reset the panel's service light. Use the due sensor in a notification
  automation if needed.

Integration options accept airflow and fan-power curves, building dimensions
and a fan minimum from 1 to 8. The default is 5; updating does not lower an
existing minimum. Set it to the commissioned ventilation minimum for the building.
The fan, number and select entities, including automation service calls, all enforce
this setting before passing a command to the library. Calculated airflow and power
are estimates based on that profile.

Existing date/interval helpers can be selected in the options when migrating a
dashboard. Entity IDs and configuration-entry IDs are preserved by this update.

The integration does not expose unverified heater enable, bypass or fault codes.
See [supported features](feature-comparison.md).
