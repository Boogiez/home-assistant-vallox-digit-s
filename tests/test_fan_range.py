"""Library levels and installation limits are independent."""

import asyncio
import importlib
from types import SimpleNamespace

import pytest
from conftest import PKG
from test_ha_boundary import Entry, Hass
from test_ha_boundary import ha_modules  # noqa: F401
from test_native_entities import coordinator
from test_native_entities import native  # noqa: F401
from test_options_flow import flow_module  # noqa: F401

features = importlib.import_module(f"{PKG}.features")
control = importlib.import_module(f"{PKG}.speed_control")
protocol = importlib.import_module(f"{PKG}.protocol")


@pytest.mark.parametrize("level", range(1, 9))
def test_all_levels_encode_and_decode(level):
    for recipient in (0x11, 0x20):
        packet = control.speed_packet(level, recipient)
        control.validate_speed_packet(packet, level)
        assert packet[:5] == bytes((1, 0x2E, recipient, 0x29, (1 << level) - 1))
        assert packet[5] == sum(packet[:5]) & 255
        assert protocol.convert(0x29, packet[4]) == level


@pytest.mark.parametrize("minimum", range(1, 9))
@pytest.mark.parametrize("level", range(1, 9))
def test_shared_boundary_enforces_every_minimum(ha_modules, minimum, level):
    async def run():
        entry = Entry()
        entry.options = {"minimum_fan_level": minimum}
        calls = []
        reader = SimpleNamespace(
            set_fan_speed=calls.append, snapshot=lambda: {"fan_speed": level}
        )
        obj = importlib.import_module(f"{PKG}.coordinator").DigitSCoordinator(
            Hass(), entry, reader
        )
        if level < minimum:
            with pytest.raises(control.SpeedControlError):
                await obj.async_set_fan_speed(level)
            assert calls == []
        else:
            await obj.async_set_fan_speed(level)
            assert calls == [level]
        assert not obj._wire_lock.locked()

    asyncio.run(run())


@pytest.mark.parametrize("minimum", range(1, 9))
def test_options_accept_full_range_and_preserve_other_settings(flow_module, minimum):
    flow = flow_module.DigitSOptionsFlow()
    flow.config_entry = SimpleNamespace(
        options={"filter_changed": "2026-10-16", "minimum_fan_level": 7}
    )
    form = asyncio.run(flow.async_step_init())
    data = form["data_schema"]({"minimum_fan_level": minimum})
    result = asyncio.run(flow.async_step_init(data))
    assert result["data"]["minimum_fan_level"] == minimum
    assert result["data"]["filter_changed"] == "2026-10-16"
    assert features.minimum_speed(result["data"]) == minimum


@pytest.mark.parametrize(
    "bad", [0, 9, -1, 1.5, False, float("nan"), float("inf"), "bad"]
)
def test_options_schema_rejects_invalid_minimum(flow_module, bad):
    import voluptuous as vol

    flow = flow_module.DigitSOptionsFlow()
    form = asyncio.run(flow.async_step_init())
    with pytest.raises(vol.Invalid):
        form["data_schema"]({"minimum_fan_level": bad})


@pytest.mark.parametrize("bad", [True, False, 0, 9, 1.5])
def test_options_flow_rejects_invalid_raw_input(flow_module, bad):
    result = asyncio.run(
        flow_module.DigitSOptionsFlow().async_step_init({"minimum_fan_level": bad})
    )
    assert result["type"] == "form" and result["errors"]["base"] == "invalid_profile"


@pytest.mark.parametrize("minimum", range(1, 9))
def test_entities_offer_the_same_configured_range(native, minimum):
    obj, calls = coordinator()
    entry = Entry()
    entry.options = {"minimum_fan_level": minimum}
    obj.data["fan_speed"] = minimum
    fan = importlib.import_module(f"{PKG}.fan").DigitSFan(obj, entry)
    number = importlib.import_module(f"{PKG}.number").DigitSSpeed(obj, entry)
    select = importlib.import_module(f"{PKG}.select").DigitSSelect(obj, entry, False)
    assert fan.speed_count == 9 - minimum
    assert number.native_min_value == minimum
    assert select.options == [features.FAN_NAMES[level] for level in range(minimum, 9)]
    assert select.current_option == features.FAN_NAMES[minimum]

    async def run():
        await fan.async_set_percentage(1)
        await number.async_set_native_value(float(minimum))
        await select.async_select_option(features.FAN_NAMES[minimum])

    asyncio.run(run())
    assert calls == [("fan", minimum)] * 3


def test_unconfigured_installations_keep_the_previous_default(flow_module):
    assert features.minimum_speed({}) == 5
    flow = flow_module.DigitSOptionsFlow()
    form = asyncio.run(flow.async_step_init())
    assert form["data_schema"]({})["minimum_fan_level"] == 5
