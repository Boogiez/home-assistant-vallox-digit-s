"""These tests load real HA; only the physical Vallox reader is simulated."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

DOMAIN = "vallox_digit_s_legacy"


class SimulatedReader:
    control_enabled = True

    def __init__(self):
        self.calls = []
        self.stopped = False
        self.values = {
            "fan_speed": 6, "heating_level": 4,
            "temperature_outdoor_air": 12, "temperature_supply_air": 18,
            "temperature_extract_air": 20, "temperature_exhaust_air": 16,
            "supply_temperature_gain": 6, "exhaust_temperature_drop": 4,
            "connection_state": "Yhteys toimii", "last_success_age": 2,
            "_sample_times": {},
        }

    def snapshot(self):
        return deepcopy(self.values)

    def sample(self):
        self.calls.append("sample")
        return self.snapshot()

    def set_fan_speed(self, level):
        self.calls.append(("fan", level))
        self.values["fan_speed"] = level

    def set_heating_level(self, level):
        self.calls.append(("heat", level))
        self.values["heating_level"] = level

    def stop(self):
        self.stopped = True

    def wait_closed(self):
        self.calls.append("closed")

    def diagnostics(self):
        return {"settings_writes_supported": True}


@pytest.fixture(autouse=True)
def enable_local_code(enable_custom_integrations):
    """Enable the project under test through the normal HA custom loader."""


@pytest.fixture
def simulated_reader(monkeypatch):
    import custom_components.vallox_digit_s_legacy as integration
    reader = SimulatedReader()
    monkeypatch.setattr(integration, "ActiveReader", lambda *args, **kwargs: reader)
    # USB discovery is a separate HA integration. Avoid scanning CI hardware;
    # the genuine USB module and serial selector are still imported.
    import homeassistant.components.usb as usb
    monkeypatch.setattr(usb, "async_setup", AsyncMock(return_value=True))
    return reader
