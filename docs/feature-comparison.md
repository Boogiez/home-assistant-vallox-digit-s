# Vallox Digit S: comparison with Helios/Vallox v2026.10.1

This integration supports the verified legacy Digit S subset. It is not a full port of the newer SE protocol. The 0.7.0rc1 baseline has run on one legacy unit; the 0.7.1b1 changes are regression-tested. See [validation](validation.md).

All 68 upstream entity definitions are included below. Optional sensors and unverified SE registers are not represented as working S features.

| Upstream entity | Candidate status | Evidence / limit |
|---|---|---|
| `temperature_outdoor_air` | verified_existing | Verified old S addresses; not upstream SE temperature addresses. |
| `temperature_supply_air` | verified_existing | Verified old S addresses; not upstream SE temperature addresses. |
| `temperature_extract_air` | verified_existing | Verified old S addresses; not upstream SE temperature addresses. |
| `temperature_exhaust_air` | verified_existing | Verified old S addresses; not upstream SE temperature addresses. |
| `post_heating_target` | bounded_alternative_rc1 | Verified A4 eight-step control. Celsius anchors 10/20/27 confirmed; intermediate labels explicit estimates, not continuous SE NTC control. |
| `boost_remaining` | external_automation_not_bundled | Use an external HA timer/automation if desired. A generic boost controller and the hardware boost register are not implemented in this release. |
| `fault_number` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `fault_text` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `analog_input` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `rh_sensor1_raw` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `rh_sensor2_raw` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `highest_humidity` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_reading_upper_byte` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_reading_lower_byte` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_setting_upper_byte` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_setting_lower_byte` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `temperature_reduction` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `temperature_gain` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `temperature_balance` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `efficiency` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `rh_sensor1` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `rh_sensor2` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_concentration` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `din_airflow_moisture` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `din_airflow_reduced` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `din_airflow_normal` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `din_airflow_boost` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `effective_airflow` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `electrical_power` | calculation_rc1 | Configured-curve estimate or temperature calculation. No measured airflow/power or isolated LTO efficiency claimed. DIN is reference-only. |
| `boost_status` | external_automation_not_bundled | Use an external HA timer/automation if desired. A generic boost controller and the hardware boost register are not implemented in this release. |
| `fault_detected` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `clean_filter` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `service_requested` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `post_heating_on` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `bypass_damper_position` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `fault_relay` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `preheating_on` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `external_boost_switch` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `co2_sensor1_present` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_sensor2_present` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_sensor3_present` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_sensor4_present` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_sensor5_present` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `co2_alarm` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `fanspeed` | verified_existing | Actual mainboard readback and bounded 5–8 writes; native fan and named select added in rc1. |
| `initial_fanspeed` | needs_hardware_verification | A9/A5 raw value exists but interpretation on this S is unverified. No guessed offset or writes. |
| `max_fanspeed` | needs_hardware_verification | A9/A5 raw value exists but interpretation on this S is unverified. No guessed offset or writes. |
| `bypass_setpoint` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `preheat_setpoint` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `post_heating_setpoint` | bounded_alternative_rc1 | Verified A4 eight-step control. Celsius anchors 10/20/27 confirmed; intermediate labels explicit estimates, not continuous SE NTC control. |
| `defrost_setpoint` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `defrost_hysteresis` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `input_fan_percent` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `output_fan_percent` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `service_interval` | local_maintenance_rc1 | Native date/interval/countdown/due entities backed by local options or existing helpers. Does not reset the device's own service counter/light. |
| `service_due_months` | local_maintenance_rc1 | Native date/interval/countdown/due entities backed by local options or existing helpers. Does not reset the device's own service counter/light. |
| `co2_setting_value` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `basic_humidity_level` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `powerstate` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `co2_indicator` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `rh_indicator` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |
| `preheat_status` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `activate_boost` | external_automation_not_bundled | Use an external HA timer/automation if desired. A generic boost controller and the hardware boost register are not implemented in this release. |
| `input_fan_off` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `output_fan_off` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `boost_mode` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `winter_mode` | needs_hardware_verification | SE register/bit or feature has not been verified on this S. Not exposed as a working setting/status. |
| `humidity_control_mode` | not_fitted_or_unverified_optional_sensor | No fitted, verified sensor on this installation; no invented entity or automatic sensor control. |

## Features requiring further device validation

- Validate S-specific heater-enable/active, summer bypass, fault/service states and fan limits against the real panel and device documentation before adding their controls.
- Calibrate intermediate temperature-request steps before claiming exact Celsius control.
- A generic, standalone boost/notification package can be added separately. It is not part of this release.

Only the supported subset is published. This comparison is an explicit record of
the differences, not a claim that all newer SE features work on the legacy S.
