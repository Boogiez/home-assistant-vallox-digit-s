"""Application-facing readings. Missing or stale values are None."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ConnectionState(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    LISTENING = "listening"
    CLOSED = "closed"


@dataclass(frozen=True)
class Sample:
    name: str
    value: float | int
    raw: int
    age_seconds: float
    received_at: str


@dataclass(frozen=True)
class Status:
    """Temperatures in Celsius; fan and temperature settings are device steps."""

    state: ConnectionState
    outdoor_temperature: float | None
    supply_temperature: float | None
    extract_temperature: float | None
    exhaust_temperature: float | None
    fan_speed: int | None
    temperature_step: int | None
    samples: tuple[Sample, ...]
    errors: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a detached, JSON-serializable copy."""
        return asdict(self)


def status_from_snapshot(snapshot: dict[str, Any], *, closed: bool = False) -> Status:
    fields = (
        ("temperature_outdoor_air", "outdoor_temperature"),
        ("temperature_supply_air", "supply_temperature"),
        ("temperature_extract_air", "extract_temperature"),
        ("temperature_exhaust_air", "exhaust_temperature"),
        ("fan_speed", "fan_speed"),
        ("heating_level", "temperature_step"),
    )
    samples = []
    for internal, public in fields:
        if internal in snapshot:
            stamp = snapshot["_sample_times"][internal]
            samples.append(
                Sample(
                    public,
                    snapshot[internal],
                    snapshot["raw_" + internal],
                    stamp["age_seconds"],
                    stamp["received_at_utc"],
                )
            )
    count = snapshot["fresh_core_values"]
    # last_error contains only register names and redacted exception class names.
    errors = tuple(
        tuple(item.split(": ", 1))
        for item in snapshot["last_error"].split("; ")
        if ": " in item
    )
    if closed:
        state = ConnectionState.CLOSED
    elif snapshot["capture_active"]:
        state = ConnectionState.LISTENING
    elif count == 0:
        state = ConnectionState.UNAVAILABLE
    elif count < 5 or errors:
        state = ConnectionState.PARTIAL
    else:
        state = ConnectionState.READY
    values = {public: snapshot.get(internal) for internal, public in fields}
    return Status(state=state, samples=tuple(samples), errors=errors, **values)
