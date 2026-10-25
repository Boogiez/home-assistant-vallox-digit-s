"""Model-independent calculations; never opens a connection or writes registers.

DIN reference formula adapted from Tom-Bom-badil/home-assistant_helios-vallox
(GPL-3.0). It is a reference calculation, not Finnish commissioning guidance.
"""
from __future__ import annotations

from datetime import date, timedelta
import math

TEMPERATURES = (None, 10, 12.5, 15, 17.5, 20, 22.5, 25, 27)
CONFIRMED_TEMPERATURE_STEPS = (1, 5, 8)
FAN_NAMES = {5: "Alennettu", 6: "Perus", 7: "Tehostettu", 8: "Maksimi"}
TEMPERATURE_NAMES = {
    level: ("" if level in CONFIRMED_TEMPERATURE_STEPS else "≈ ")
    + f"{TEMPERATURES[level]:g}".replace(".", ",") + " °C"
    for level in range(1, 9)
}


def finite(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def parse_curve(value):
    """Accept upstream's nine entries (leading zero) or eight speed entries."""
    if value in (None, ""):
        return None
    raw = value.split(",") if isinstance(value, str) else value
    if not isinstance(raw, (tuple, list)):
        raise ValueError("Curve must contain eight values, optionally a leading zero")
    values = [finite(x) for x in raw]
    if len(values) == 8:
        values.insert(0, 0.0)
    if (len(values) != 9 or any(x is None or x < 0 or x > 10000 for x in values)
            or values[0] != 0 or any(a > b for a, b in zip(values, values[1:]))
            or values[-1] <= 0):
        raise ValueError("Curve must be nonnegative, increasing and start with zero")
    return tuple(values)


def checked_options(options):
    result = dict(options)
    for key, low, high in (("house_area", 0, 10000), ("house_volume", 0, 100000),
                          ("isolation_factor", 0, 1), ("heating_power", 0, 10000),
                          ("minimum_fan_level", 5, 8), ("filter_interval_days", 1, 730)):
        if key not in result:
            continue
        value = finite(result[key])
        if value is None or not low <= value <= high:
            raise ValueError(key)
        if key in ("minimum_fan_level", "filter_interval_days") and not value.is_integer():
            raise ValueError(key)
    for key in ("airflow_per_mode", "power_per_mode"):
        parse_curve(result.get(key))
    for key, domains in (("filter_date_entity", ("input_text", "input_datetime")),
                         ("filter_interval_entity", ("input_number",))):
        entity = result.get(key, "")
        if entity and (not isinstance(entity, str) or entity.split(".")[0] not in domains
                       or len(entity.split(".")) != 2 or not entity.split(".")[1]):
            raise ValueError(key)
    value = result.get("filter_changed", "")
    if value:
        date.fromisoformat(value)
    return result


def minimum_speed(options):
    value = finite(options.get("minimum_fan_level", 5))
    return int(value) if value is not None and value.is_integer() and 5 <= value <= 8 else 5


def speed_from_percentage(value, minimum):
    percent = finite(value)
    if percent is None or not 0 < percent <= 100:
        raise ValueError("Fan percentage must be above zero; shutdown is not supported")
    return min(8, minimum + math.ceil(percent * (9 - minimum) / 100) - 1)


def percentage_from_speed(level, minimum):
    speed = finite(level)
    if speed is None or not speed.is_integer() or not 1 <= speed <= 8:
        return None
    if speed < minimum:
        return None  # do not misrepresent an external, lower speed as the minimum
    return int(100 * (int(speed) - minimum + 1) / (9 - minimum))


def maintenance(options, today, state_value=lambda _entity: None):
    """Read existing helpers when configured; do not duplicate their authority."""
    changed = (state_value(options["filter_date_entity"])
               if options.get("filter_date_entity") else options.get("filter_changed"))
    interval = (state_value(options["filter_interval_entity"])
                if options.get("filter_interval_entity") else options.get("filter_interval_days", 120))
    result = {"filter_last_changed": None, "filter_due_date": None,
              "filter_days_remaining": None, "filter_due": None,
              "filter_interval_days": None}
    days = finite(interval)
    if days is None or not days.is_integer() or not 1 <= days <= 730:
        return result
    result["filter_interval_days"] = int(days)
    try:
        changed_date = date.fromisoformat(str(changed)[:10])
    except (ValueError, TypeError):
        return result
    if changed_date > today:
        return result  # future/invalid dates must not suppress an overdue warning
    due = changed_date + timedelta(days=int(days))
    result.update(filter_last_changed=changed_date, filter_due_date=due,
                  filter_days_remaining=(due - today).days, filter_due=due <= today)
    return result


def derived_values(data, options, today, state_value=lambda _entity: None):
    result = maintenance(options, today, state_value)
    level = finite(data.get("fan_speed"))
    if level is not None and level.is_integer() and 1 <= level <= 8:
        level = int(level)
        result["fan_mode_name"] = FAN_NAMES.get(level, "Ulkoinen alennus")
        for source, output in (("airflow_per_mode", "airflow_estimate"),
                               ("power_per_mode", "fan_power_estimate")):
            try:
                curve = parse_curve(options.get(source))
            except ValueError:
                curve = None
            if curve:
                result[output] = curve[level]
        if "airflow_estimate" in result:
            q = result["airflow_estimate"]
            result["airflow_lps_estimate"] = round(q / 3.6, 1)
            volume = finite(options.get("house_volume"))
            if volume and volume > 0:
                result["air_changes_estimate"] = round(q / volume, 3)
    # Preserve the reader's synchronized-sample gate. Missing/stale deltas stay unknown.
    gain, reduction = finite(data.get("supply_temperature_gain")), finite(data.get("exhaust_temperature_drop"))
    times = data.get("_sample_times", {})
    names = ("temperature_outdoor_air", "temperature_supply_air", "temperature_extract_air", "temperature_exhaust_air")
    stamps = [times.get(k, {}).get("received_at_utc") for k in names]
    coherent = all(stamps) and len(set(stamps)) == 1
    # Reader polls successive sensors, so allow up to ten seconds of UTC skew.
    if all(stamps):
        from datetime import datetime
        try:
            sample_times = [datetime.fromisoformat(s).timestamp() for s in stamps]
            coherent = max(sample_times) - min(sample_times) <= 10
        except (TypeError, ValueError, OverflowError):
            coherent = False
    if coherent and gain is not None and reduction is not None:
        result["temperature_balance"] = round(gain - reduction, 2)
        out, extract = finite(data.get(names[0])), finite(data.get(names[2]))
        if out is not None and extract is not None and extract - out >= 5:
            result["exhaust_temperature_ratio"] = round(100 * reduction / (extract - out), 1)
        q = result.get("airflow_estimate")
        if q is not None:
            result["supply_heat_gain_estimate"] = round(0.34 * q * gain)
            result["exhaust_heat_recovered_estimate"] = round(0.34 * q * reduction)
    area, isolation = finite(options.get("house_area")), finite(options.get("isolation_factor", .4))
    if area and 0 < area <= 1000 and isolation is not None and 0 <= isolation <= 1:
        reference = round(-.001 * area ** 2 + 1.15 * area + 20, 9)
        for key, factor in (("moisture", isolation), ("reduced", .7), ("normal", 1), ("boost", 1.15)):
            result["din_airflow_" + key] = int(factor * reference)
    heating = finite(data.get("heating_level"))
    if heating is not None and heating.is_integer() and 1 <= heating <= 8:
        result["post_heating_target_estimate"] = TEMPERATURES[int(heating)]
    result["profile_configured"] = bool(options.get("airflow_per_mode") or options.get("power_per_mode"))
    result["connection_ok"] = data.get("connection_state") == "Yhteys toimii"
    return result
