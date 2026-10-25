"""Regression tests for defects found in the publication audit."""
import asyncio
import importlib
from types import SimpleNamespace

import pytest

from conftest import PKG
from test_ha_boundary import ha_modules, Hass, Entry
from test_native_entities import native, coordinator


@pytest.mark.parametrize("value", [5, 6, 6.5, True, None, 9])
def test_configured_minimum_applies_at_coordinator_boundary(ha_modules, value):
    async def run():
        module = importlib.import_module(f"{PKG}.coordinator")
        entry = Entry()
        entry.options = {"minimum_fan_level": 7}
        calls = []
        reader = SimpleNamespace(set_fan_speed=lambda level: calls.append(level))
        obj = module.DigitSCoordinator(Hass(), entry, reader)
        with pytest.raises(importlib.import_module(f"{PKG}.speed_control").SpeedControlError):
            await obj.async_set_fan_speed(value)
        assert not calls and not obj._wire_lock.locked()
    asyncio.run(run())


def test_number_uses_configured_floor_without_affecting_temperature(native):
    module = importlib.import_module(f"{PKG}.number")
    obj, _ = coordinator()
    entry = Entry()
    entry.options = {"minimum_fan_level": 7}
    assert module.DigitSSpeed(obj, entry).native_min_value == 7
    assert module.DigitSHeating(obj, entry).native_min_value == 1


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
def test_failed_initial_refresh_closes_reader(ha_modules, monkeypatch, failure):
    from conftest import ROOT
    module_name = f"{PKG}.setup_under_test"
    path = ROOT / "custom_components" / PKG / "__init__.py"
    loader = importlib.machinery.SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_loader(module_name, loader, is_package=False)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    stopped = []
    class Coordinator:
        def __init__(self, *args): pass
        def signal_stop(self): pass
        async def async_config_entry_first_refresh(self): raise failure()
        async def async_stop(self): stopped.append(True)
    monkeypatch.setattr(module, "retire_obsolete_entities", lambda *args: None)
    monkeypatch.setattr(module, "ActiveReader", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "DigitSCoordinator", Coordinator)
    hass = Hass()
    hass.bus = SimpleNamespace(async_listen_once=lambda *args: lambda: None)
    entry = SimpleNamespace(entry_id="failed", data={"connection": "test"}, async_on_unload=lambda fn: None)
    with pytest.raises(failure):
        asyncio.run(module.async_setup_entry(hass, entry))
    assert stopped == [True] and not hass.data.get(PKG)
