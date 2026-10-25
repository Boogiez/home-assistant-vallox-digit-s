"""HA interface doubles: no actual HA runtime or device installation claimed."""
import asyncio
from datetime import date
from enum import IntFlag
import importlib
from types import ModuleType, SimpleNamespace
import sys
import pytest
from conftest import PKG
from test_ha_boundary import ha_modules, Hass, Entry


@pytest.fixture
def native(ha_modules, monkeypatch):
    for name, cls in (("fan", "FanEntity"), ("select", "SelectEntity"),
                      ("binary_sensor", "BinarySensorEntity"), ("date", "DateEntity"),
                      ("number", "NumberEntity")):
        module = ModuleType("homeassistant.components." + name)
        setattr(module, cls, type(cls, (), {}))
        monkeypatch.setitem(sys.modules, module.__name__, module)
    class Features(IntFlag): SET_SPEED=1; TURN_ON=2; TURN_OFF=4; PRESET_MODE=8
    sys.modules['homeassistant.components.fan'].FanEntityFeature=Features
    sys.modules['homeassistant.components.number'].NumberMode=SimpleNamespace(BOX='box')
    return ha_modules


def coordinator():
    calls=[]
    async def set_fan(value): calls.append(('fan',value))
    async def set_heat(value): calls.append(('heat',value))
    async def set_date(value): calls.append(('date',value))
    async def set_interval(value): calls.append(('interval',value))
    return SimpleNamespace(data={'fan_speed':6,'heating_level':4,'filter_last_changed':date(2026,1,1),'filter_interval_days':120},
        reader=SimpleNamespace(control_enabled=True),_stopping=False,capture_pending=False,
        _wire_lock=SimpleNamespace(locked=lambda:False),async_set_fan_speed=set_fan,
        async_set_heating_level=set_heat,async_set_filter_date=set_date,async_set_filter_interval=set_interval),calls


def test_native_fan_uses_bounded_speed_service_and_does_not_advertise_off(native):
    m=importlib.import_module(f'{PKG}.fan'); c,calls=coordinator(); e=Entry();e.options={'minimum_fan_level':6}
    fan=m.DigitSFan(c,e)
    assert fan.available and fan.is_on and fan.speed_count==3 and fan.percentage==33
    assert fan._attr_supported_features==sys.modules['homeassistant.components.fan'].FanEntityFeature.SET_SPEED
    asyncio.run(fan.async_set_percentage(67));assert calls==[('fan',8)]
    with pytest.raises(native['homeassistant.exceptions'].HomeAssistantError):asyncio.run(fan.async_set_percentage(0))
    assert len(calls)==1


def test_select_uses_actual_readback_and_fails_closed(native):
    m=importlib.import_module(f'{PKG}.select');c,calls=coordinator();e=Entry();e.options={'minimum_fan_level':6}
    heat=m.DigitSSelect(c,e,True);fan=m.DigitSSelect(c,e,False)
    assert heat.current_option=='≈ 17,5 °C' and fan.options==['Perus','Tehostettu','Maksimi']
    asyncio.run(heat.async_select_option('20 °C'));assert calls==[('heat',5)]
    assert heat.current_option=='≈ 17,5 °C'  # no optimistic, fabricated setting
    with pytest.raises(native['homeassistant.exceptions'].HomeAssistantError):asyncio.run(fan.async_select_option('Alennettu'))
    c.data.pop('heating_level');assert not heat.available
    assert heat.extra_state_attributes['heater_enable_control'] is False


def test_local_date_and_interval_are_native_entities_not_machine_registers(native):
    c,calls=coordinator();e=Entry()
    d=importlib.import_module(f'{PKG}.date').DigitSFilterDate(c,e)
    n=importlib.import_module(f'{PKG}.number').DigitSFilterInterval(c,e)
    assert d.native_value==date(2026,1,1) and n.native_value==120
    asyncio.run(d.async_set_value(date(2026,2,1)))
    asyncio.run(n.async_set_native_value(90))
    assert calls==[('date',date(2026,2,1)),('interval',90)]


def test_unknown_filter_state_is_not_false(native):
    c,_=coordinator();e=Entry()
    obj=importlib.import_module(f'{PKG}.binary_sensor').DigitSBinary(c,e,'filter_due','Due','problem')
    assert obj.is_on is None and not obj.available
    c.data['filter_due']=False;assert obj.is_on is False and obj.available


def test_filter_helper_updates_never_call_reader_or_write_a_register(native, make_reader):
    async def run():
        m=importlib.import_module(f'{PKG}.coordinator');h=Hass();e=Entry()
        e.options={'filter_date_entity':'input_text.filter','filter_interval_entity':'input_number.interval'}
        values={'input_text.filter':'2026-01-01','input_number.interval':'120'}
        h.states=SimpleNamespace(get=lambda id:SimpleNamespace(state=values[id]) if id in values else None)
        called=[]
        async def call(domain, service, data, blocking):
            called.append((domain,service,data));values[data['entity_id']]=str(data['value'])
        h.services=SimpleNamespace(async_call=call)
        reader,port=make_reader();c=m.DigitSCoordinator(h,e,reader)
        await c.async_set_filter_date(date(2026,10,16));await c.async_set_filter_interval(120)
        assert called[0][:2]==('input_text','set_value') and called[1][:2]==('input_number','set_value')
        assert c.data['filter_days_remaining']==113 and not port.sent
        before=len(called)
        for bad in (0,2.5,True,float('nan')):
            with pytest.raises(native['homeassistant.exceptions'].HomeAssistantError):await c.async_set_filter_interval(bad)
        with pytest.raises(native['homeassistant.exceptions'].HomeAssistantError):await c.async_set_filter_date(date(2027,1,1))
        assert len(called)==before and not port.sent
    asyncio.run(run())


def test_calculation_options_apply_without_bus_io(native, make_reader):
    async def run():
        m=importlib.import_module(f'{PKG}.coordinator');h=Hass();e=Entry();e.options={}
        reader,port=make_reader();c=m.DigitSCoordinator(h,e,reader)
        await c.async_options_updated(h,e)
        assert c.data['profile_configured'] is False and not port.sent
    asyncio.run(run())
