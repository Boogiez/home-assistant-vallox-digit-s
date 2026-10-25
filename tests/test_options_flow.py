"""Exercise the actual voluptuous schema and options-flow branch decisions."""
import asyncio
import importlib
from types import ModuleType, SimpleNamespace
import sys
import pytest
from conftest import PKG
from test_ha_boundary import ha_modules


@pytest.fixture
def flow_module(ha_modules, monkeypatch):
    class Flow:
        def __init_subclass__(cls, **kwargs): pass
        def async_show_form(self, **kwargs): return {"type":"form",**kwargs}
        def async_create_entry(self, **kwargs): return {"type":"create_entry",**kwargs}
    class Options(Flow):
        config_entry=SimpleNamespace(options={})
    ce=ha_modules['homeassistant.config_entries'];ce.ConfigFlow=Flow;ce.OptionsFlow=Options
    ha_modules['homeassistant'].config_entries=ce
    selector=ModuleType('homeassistant.helpers.selector');selector.SerialPortSelector=lambda:str
    monkeypatch.setitem(sys.modules,selector.__name__,selector)
    monkeypatch.delitem(sys.modules,f'{PKG}.config_flow',raising=False)
    return importlib.import_module(f'{PKG}.config_flow')


def test_profile_form_accepts_upstream_curves_and_retains_local_date(flow_module):
    flow=flow_module.DigitSOptionsFlow();flow.config_entry=SimpleNamespace(options={'filter_changed':'2026-01-01'})
    form=asyncio.run(flow.async_step_init())
    data=form['data_schema']({'house_area':100,'house_volume':250,'airflow_per_mode':'1,2,3,4,5,6,7,8','power_per_mode':'0,10,20,30,40,50,60,70,80','minimum_fan_level':6})
    saved=asyncio.run(flow.async_step_init(data))
    assert saved['type']=='create_entry' and saved['data']['filter_changed']=='2026-01-01'
    assert saved['data']['minimum_fan_level']==6


@pytest.mark.parametrize('data',[{'airflow_per_mode':'1,2,3'},{'filter_date_entity':'switch.heater'},{'filter_interval_entity':'number.fan'},{'house_volume':float('nan')},{'minimum_fan_level':4}])
def test_bad_profile_stays_in_form(flow_module,data):
    result=asyncio.run(flow_module.DigitSOptionsFlow().async_step_init(data))
    assert result['type']=='form' and result['errors']['base']=='invalid_profile'


def test_options_flow_registered_without_touching_connection(flow_module):
    assert isinstance(flow_module.DigitSConfigFlow.async_get_options_flow(None),flow_module.DigitSOptionsFlow)


def test_both_translations_include_exact_options_schema_keys(flow_module):
    import json
    from conftest import ROOT
    form=asyncio.run(flow_module.DigitSOptionsFlow().async_step_init())
    keys={str(key) for key in form['data_schema'].schema}
    for name in ('strings.json','translations/en.json','translations/fi.json'):
        data=json.loads((ROOT/'custom_components'/PKG/name).read_text(encoding="utf-8"))
        assert set(data['options']['step']['init']['data'])==keys
