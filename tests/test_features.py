"""Engineering expectations, uncertainty and invalid-input boundaries."""
from datetime import date
import importlib
import math
import pytest
from conftest import PKG

f = importlib.import_module(f"{PKG}.features")


def sample():
    data = dict(fan_speed=6, heating_level=4, connection_state="Yhteys toimii",
                supply_temperature_gain=7, exhaust_temperature_drop=5,
                temperature_outdoor_air=11, temperature_supply_air=18,
                temperature_extract_air=20, temperature_exhaust_air=15)
    data["_sample_times"] = {key: {"received_at_utc": "2026-01-01T00:00:00+00:00"} for key in data if key.startswith("temperature_")}
    return data


def test_physical_units_and_no_fabricated_heater_consumption():
    options = {"airflow_per_mode": "50,80,110,140,170,200,230,260",
               "power_per_mode": "20,40,60,80,100,120,140,160", "house_volume": 400}
    result = f.derived_values(sample(), options, date(2026, 1, 1))
    assert result["airflow_estimate"] == 200
    assert result["airflow_lps_estimate"] == 55.6
    assert result["air_changes_estimate"] == .5
    assert result["fan_power_estimate"] == 120
    assert result["temperature_balance"] == 2
    assert result["supply_heat_gain_estimate"] == 476
    assert result["exhaust_heat_recovered_estimate"] == 340
    assert result["exhaust_temperature_ratio"] == 55.6
    assert not {"heater_power", "heater_on", "bypass", "fault_detected"} & result.keys()


def test_unknown_profile_does_not_create_measurements():
    result = f.derived_values(sample(), {}, date(2026, 1, 1))
    assert not result["profile_configured"]
    assert "airflow_estimate" not in result and "fan_power_estimate" not in result
    assert "supply_heat_gain_estimate" not in result


@pytest.mark.parametrize("bad", ["", "unknown", "unavailable", None, True, float("nan"), float("inf"), 6.5, 0, 9])
def test_missing_or_invalid_speed_never_becomes_airflow(bad):
    data = sample(); data["fan_speed"] = bad
    result = f.derived_values(data, {"airflow_per_mode": "1,2,3,4,5,6,7,8"}, date(2026, 1, 1))
    assert "airflow_estimate" not in result


@pytest.mark.parametrize("curve", ["1,2", "0,1,2,3,4,5,6,7,0", "-1,2,3,4,5,6,7,8", "1,2,3,4,5,6,7,nan", [0]*9, True])
def test_corrupt_curves_are_rejected(curve):
    with pytest.raises(ValueError): f.parse_curve(curve)


def test_upstream_eight_and_nine_entry_curves_are_equivalent():
    assert f.parse_curve("1,2,3,4,5,6,7,8") == f.parse_curve("0,1,2,3,4,5,6,7,8")


def test_sensor_sample_skew_and_missing_sensors_suppress_heat_calculations():
    data = sample()
    data["_sample_times"]["temperature_exhaust_air"]["received_at_utc"] = "2026-01-01T00:00:11+00:00"
    result = f.derived_values(data, {}, date(2026, 1, 1))
    assert "temperature_balance" not in result and "exhaust_temperature_ratio" not in result
    data = sample(); data.pop("exhaust_temperature_drop")
    assert "temperature_balance" not in f.derived_values(data, {}, date(2026, 1, 1))


def test_near_equal_indoor_and_outdoor_temperatures_hide_unstable_ratios():
    data = sample(); data["temperature_extract_air"] = 12
    assert "exhaust_temperature_ratio" not in f.derived_values(data, {}, date(2026, 1, 1))


def test_din_is_a_reference_calculation_not_control_minimum():
    result = f.derived_values({}, {"house_area": 100, "isolation_factor": .4}, date(2026, 1, 1))
    assert [result["din_airflow_"+k] for k in ("moisture", "reduced", "normal", "boost")] == [50, 87, 125, 143]
    assert "fan_speed" not in result


def test_filter_deadline_and_overdue_values_include_leap_year():
    opts = {"filter_changed": "2024-02-28", "filter_interval_days": 2}
    assert f.maintenance(opts, date(2024, 2, 29))["filter_days_remaining"] == 1
    assert f.maintenance(opts, date(2024, 3, 1))["filter_due"] is True
    assert f.maintenance(opts, date(2024, 3, 2))["filter_days_remaining"] == -1


@pytest.mark.parametrize("changed", [None, "unknown", "2026-02-30", "2027-01-01"])
def test_invalid_or_future_filter_dates_do_not_report_everything_ok(changed):
    result = f.maintenance({"filter_changed": changed}, date(2026, 1, 1))
    assert result["filter_due"] is None and result["filter_due_date"] is None


def test_helper_authority_wins_over_old_internal_values():
    values = {"input_text.change": "2026-01-01", "input_number.interval": "30"}
    result = f.maintenance({"filter_changed": "2025-01-01", "filter_date_entity": "input_text.change",
                            "filter_interval_entity": "input_number.interval"}, date(2026, 1, 15), values.get)
    assert result["filter_days_remaining"] == 16
    values["input_number.interval"] = "unavailable"
    assert f.maintenance({"filter_date_entity": "input_text.change", "filter_interval_entity": "input_number.interval"}, date(2026, 1, 15), values.get)["filter_due"] is None


@pytest.mark.parametrize("options", [{"house_area": float("nan")}, {"minimum_fan_level": 0}, {"minimum_fan_level": 5.5}, {"filter_interval_days": 0}, {"filter_date_entity": "switch.heat"}, {"filter_interval_entity": "number.fan"}])
def test_options_cannot_inject_unsafe_helper_targets_or_nonfinite_data(options):
    with pytest.raises(ValueError): f.checked_options(options)


def test_native_fan_percent_is_a_discrete_position_not_power_and_never_off():
    assert [f.speed_from_percentage(p, 6) for p in (1, 33, 34, 66, 67, 100)] == [6,6,7,7,8,8]
    assert [f.percentage_from_speed(n, 6) for n in (6,7,8)] == [33,66,100]
    assert f.percentage_from_speed(5, 6) is None
    for bad in (0, -1, 101, None, True, float("nan")):
        with pytest.raises(ValueError): f.speed_from_percentage(bad, 6)


def test_native_fan_current_percentage_round_trips_without_changing_speed():
    for minimum in range(1,9):
        for level in range(minimum,9):
            assert f.speed_from_percentage(f.percentage_from_speed(level,minimum),minimum)==level


def test_celsius_unknowns_remain_explicit():
    assert f.TEMPERATURE_NAMES[5] == "20 °C"
    assert f.TEMPERATURE_NAMES[4] == "≈ 17,5 °C"
    assert all(f.TEMPERATURE_NAMES[n].startswith("≈") for n in (2,3,4,6,7))
