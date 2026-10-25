"""Real HA setup, state machine, service, options and unload integration tests."""
import pytest

from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.fan import FanEntityFeature
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "vallox_digit_s_legacy"


async def setup(hass):
    entry = MockConfigEntry(domain=DOMAIN, title="Vallox Digit S",
        data={"connection": "socket://vallox-gateway.invalid:8899"},
        options={"filter_changed": "2026-10-16", "filter_interval_days": 120})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id(hass, entry, domain, key):
    result = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert result is not None, (domain, key)
    return result


async def test_setup_states_and_unload(hass, simulated_reader, freezer):
    freezer.move_to("2026-10-25T12:00:00+00:00")
    entry = await setup(hass)
    for key, expected in (("temperature_outdoor_air", "12"), ("temperature_supply_air", "18"),
                          ("temperature_extract_air", "20"), ("temperature_exhaust_air", "16")):
        state = hass.states.get(entity_id(hass, entry, "sensor", key))
        assert state.state == expected and state.attributes["unit_of_measurement"] == "°C"
    assert hass.states.get(entity_id(hass, entry, "sensor", "filter_due_date")).state == "2027-02-13"
    assert hass.states.get(entity_id(hass, entry, "sensor", "filter_days_remaining")).state == "111"
    assert simulated_reader.calls == ["sample"]  # setup never writes a setting
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert simulated_reader.stopped and "closed" in simulated_reader.calls
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_real_services_and_shared_minimum(hass, simulated_reader):
    entry = await setup(hass)
    number = entity_id(hass, entry, "number", "fan_speed_control")
    fan = entity_id(hass, entry, "fan", "fan")
    assert hass.states.get(fan).attributes["supported_features"] == FanEntityFeature.SET_SPEED
    select = entity_id(hass, entry, "select", "temperature_select")
    await hass.services.async_call("fan", "set_percentage", {"entity_id": fan, "percentage": 100}, blocking=True)
    assert ("fan", 8) in simulated_reader.calls
    assert hass.states.get(number).state == "8"
    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "20 °C"}, blocking=True)
    assert ("heat", 5) in simulated_reader.calls
    hass.config_entries.async_update_entry(entry, options={**entry.options, "minimum_fan_level": 7})
    await hass.async_block_till_done()
    assert hass.states.get(number).attributes["min"] == 7
    before = list(simulated_reader.calls)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 6}, blocking=True)
    assert before == simulated_reader.calls
    await hass.config_entries.async_unload(entry.entry_id)


async def test_local_maintenance_and_options_never_write_device(hass, simulated_reader, freezer):
    freezer.move_to("2026-10-25T12:00:00+00:00")
    entry = await setup(hass)
    await hass.services.async_call("date", "set_value", {
        "entity_id": entity_id(hass, entry, "date", "filter_change_date"), "date": "2026-10-20"}, blocking=True)
    await hass.services.async_call("number", "set_value", {
        "entity_id": entity_id(hass, entry, "number", "filter_interval"), "value": 90}, blocking=True)
    await hass.async_block_till_done()
    assert entry.options["filter_changed"] == "2026-10-20"
    assert entry.options["filter_interval_days"] == 90
    assert not [call for call in simulated_reader.calls if isinstance(call, tuple)]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input={
        "minimum_fan_level": 6, "airflow_per_mode": "50,80,110,140,170,200,230,260"})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["filter_changed"] == "2026-10-20"
    assert not [call for call in simulated_reader.calls if isinstance(call, tuple)]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow_rejects_unsupported_connection(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"connection": "http://example.invalid"})
    assert result["type"] == "form" and result["errors"]["connection"] == "invalid_connection"


@pytest.mark.parametrize("minimum", [1, 4, 8])
async def test_configurable_minimum_through_all_real_services(hass, simulated_reader, minimum):
    entry = await setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"],
        user_input={"minimum_fan_level": minimum})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    number = entity_id(hass, entry, "number", "fan_speed_control")
    fan = entity_id(hass, entry, "fan", "fan")
    select = entity_id(hass, entry, "select", "fan_mode_select")
    assert hass.states.get(number).attributes["min"] == minimum
    options = hass.states.get(select).attributes["options"]
    assert len(options) == 9 - minimum
    for domain, service, data in (
        ("fan", "set_percentage", {"entity_id": fan, "percentage": 1}),
        ("number", "set_value", {"entity_id": number, "value": minimum}),
        ("select", "select_option", {"entity_id": select, "option": options[0]}),
    ):
        await hass.services.async_call(domain, service, data, blocking=True)
        assert simulated_reader.calls[-1] == ("fan", minimum)
        assert hass.states.get(number).state == str(minimum)
    before = list(simulated_reader.calls)
    for domain, service, data in (
        ("fan", "set_percentage", {"entity_id": fan, "percentage": 0}),
        ("number", "set_value", {"entity_id": number, "value": minimum - 1}),
        ("select", "select_option", {"entity_id": select, "option": "below minimum"}),
    ):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(domain, service, data, blocking=True)
    assert simulated_reader.calls == before
    await hass.config_entries.async_unload(entry.entry_id)
