"""HA-boundary tests with explicit API doubles, NOT a real Home Assistant run."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import pytest
from conftest import ROOT, PKG


@pytest.fixture
def ha_modules(monkeypatch):
    names = ["homeassistant", "homeassistant.core", "homeassistant.config_entries",
             "homeassistant.const", "homeassistant.components", "homeassistant.components.sensor",
             "homeassistant.components.button", "homeassistant.helpers",
             "homeassistant.helpers.entity", "homeassistant.helpers.entity_registry",
             "homeassistant.helpers.update_coordinator", "homeassistant.exceptions",
             "homeassistant.util", "homeassistant.util.dt"]
    modules = {}
    for name in names:
        mod = ModuleType(name); mod.__path__ = []
        monkeypatch.setitem(sys.modules, name, mod)
        modules[name] = mod
    class Description:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():setattr(self, key, value)
            if not hasattr(self,"device_class"):self.device_class=None
    class SensorEntity: pass
    class ButtonEntity: pass
    class DeviceClass(StrEnum): TEMPERATURE="temperature"; TIMESTAMP="timestamp"
    class StateClass(StrEnum): MEASUREMENT="measurement"
    class EntityCategory(StrEnum): DIAGNOSTIC="diagnostic"; CONFIG="config"
    class Disabler(StrEnum): INTEGRATION="integration"; USER="user"
    class BaseCoordinator:
        def __init__(self, hass, logger, **kwargs):
            self.hass=hass; self.data=None; self.last_update_success=True
            self.update_interval=kwargs.get("update_interval")
        def async_set_updated_data(self,data):self.data=data
        async def async_config_entry_first_refresh(self):self.data=await self._async_update_data()
    class CoordinatorEntity:
        def __init__(self, coordinator):self.coordinator=coordinator
    sensor=modules['homeassistant.components.sensor']
    sensor.SensorEntity=SensorEntity; sensor.SensorEntityDescription=Description
    sensor.SensorDeviceClass=DeviceClass; sensor.SensorStateClass=StateClass
    button=modules['homeassistant.components.button']
    button.ButtonEntity=ButtonEntity; button.ButtonEntityDescription=Description
    modules['homeassistant.helpers.entity'].EntityCategory=EntityCategory
    coord=modules['homeassistant.helpers.update_coordinator']
    coord.DataUpdateCoordinator=BaseCoordinator; coord.CoordinatorEntity=CoordinatorEntity
    er=modules['homeassistant.helpers.entity_registry']
    er.RegistryEntryDisabler=Disabler
    modules['homeassistant.core'].HomeAssistant=object
    modules['homeassistant.core'].callback=lambda fn:fn
    modules['homeassistant.config_entries'].ConfigEntry=object
    modules['homeassistant.const'].EVENT_HOMEASSISTANT_STOP='homeassistant_stop'
    modules['homeassistant.exceptions'].HomeAssistantError=type('HomeAssistantError',(Exception,),{})
    modules['homeassistant.util'].dt=modules['homeassistant.util.dt']
    modules['homeassistant.util.dt'].now=lambda:datetime(2026,10,23,tzinfo=timezone.utc)
    for name in ['sensor','button','coordinator','migration','diagnostics','entity','fan','select','date','binary_sensor','number','config_flow']:
        monkeypatch.delitem(sys.modules,f'{PKG}.{name}',raising=False)
    return modules


class Hass:
    def __init__(self):self.data={};self.jobs=[];self.states=SimpleNamespace(get=lambda _id:None)
    async def async_add_executor_job(self, target, *args):
        self.jobs.append(target.__name__)
        return target(*args)
    def async_create_background_task(self,target,name,eager_start=True):
        return asyncio.create_task(target,name=name)


class Entry:
    entry_id='entry-test'
    options={}
    def async_create_background_task(self,hass,target,name,eager_start=True):
        return hass.async_create_background_task(target,name,eager_start)


def test_no_extra_wire_reads_for_five_second_status_ticks(ha_modules, make_reader):
    async def run():
        mod=importlib.import_module(f'{PKG}.coordinator')
        reader,port=make_reader()
        hass=Hass(); coordinator=mod.DigitSCoordinator(hass,Entry(),reader)
        await coordinator.async_config_entry_first_refresh()
        assert len(port.sent)==7
        for _ in range(12):await coordinator._async_update_data()
        assert len(port.sent)==7 and hass.jobs.count('sample')==1
        coordinator._next_poll=0
        await coordinator._async_update_data()
        assert len(port.sent)==14
        await coordinator.async_stop()
        assert reader._stop.is_set()
    asyncio.run(run())


def test_capture_suppresses_polling_and_can_only_start_once(ha_modules, make_reader):
    async def run():
        mod=importlib.import_module(f'{PKG}.coordinator')
        reader,port=make_reader()
        hass=Hass(); coordinator=mod.DigitSCoordinator(hass,Entry(),reader)
        await coordinator.async_start_capture()
        task=coordinator._capture_task
        await coordinator.async_start_capture()
        assert coordinator._capture_task is task
        assert coordinator.capture_pending
        await coordinator._async_update_data()
        assert not port.sent
        await task
        assert not port.sent
        assert reader.snapshot()['capture_status']=='Tallennus valmis'
        await coordinator._async_update_data()
        assert len(port.sent)==7
        await coordinator.async_stop()
    asyncio.run(run())


def test_stopping_queued_capture_prevents_open(ha_modules, make_reader):
    async def run():
        mod=importlib.import_module(f'{PKG}.coordinator')
        reader,port=make_reader()
        coordinator=mod.DigitSCoordinator(Hass(),Entry(),reader)
        await coordinator.async_start_capture()
        await coordinator.async_stop()
        assert not port.opened and not port.sent
        await coordinator.async_start_capture()
        assert not coordinator.capture_pending
    asyncio.run(run())


def test_migration_scoped_and_nondestructive(ha_modules):
    mod=importlib.import_module(f'{PKG}.migration')
    er=ha_modules['homeassistant.helpers.entity_registry']
    def item(key, platform=PKG, disabled=None, entry='entry-test'):
        return SimpleNamespace(platform=platform,unique_id=f'{entry}_{key}',
                               entity_id=f'sensor.{entry}_{key}',disabled_by=disabled)
    items=[item('basic_fan_speed'),item('maximum_fan_speed'),item('valid_telegrams'),
           item('fan_speed'),item('temperature_outdoor_air'),item('other'),
           item('legacy_telegrams',disabled='user'),item('basic_fan_speed',platform='other'),
           item('basic_fan_speed',entry='other-entry')]
    changed=[]
    registry=SimpleNamespace(async_update_entity=lambda eid,**kw:changed.append((eid,kw)))
    er.async_get=lambda hass:registry
    er.async_entries_for_config_entry=lambda reg, entry:items
    mod.retire_obsolete_entities(Hass(),Entry())
    assert {eid for eid,_ in changed} == {'sensor.entry-test_basic_fan_speed',
        'sensor.entry-test_maximum_fan_speed','sensor.entry-test_valid_telegrams'}
    assert all(change['disabled_by']=='integration' for _,change in changed)


def test_sensor_identity_values_attributes_and_timestamp(ha_modules, make_reader, clock):
    mod=importlib.import_module(f'{PKG}.sensor')
    reader,port=make_reader(); reader.sample()
    port.responses[0x29]=0x3F;reader.sample()
    coordinator=SimpleNamespace(data=reader.snapshot())
    sensors={d.key:mod.DigitSSensor(coordinator,Entry(),d) for d in mod.SENSORS}
    assert len(sensors)==len(mod.SENSORS)
    assert sensors['fan_speed']._attr_unique_id=='entry-test_fan_speed'
    assert sensors['fan_speed'].native_value==6
    assert sensors['register_a9_raw'].native_value==15
    assert sensors['register_a9_raw'].extra_state_attributes['last_raw_byte']=='0x0F'
    assert sensors['fan_speed_last_change'].native_value.tzinfo is not None
    before=sensors['temperature_outdoor_air'].extra_state_attributes
    clock.advance(5);coordinator.data=reader.snapshot()
    assert sensors['temperature_outdoor_air'].extra_state_attributes==before
    assert 'basic_fan_speed' not in sensors and 'maximum_fan_speed' not in sensors


def test_buttons_only_trigger_local_diagnostics(ha_modules, make_reader):
    async def run():
        cm=importlib.import_module(f'{PKG}.coordinator')
        bm=importlib.import_module(f'{PKG}.button')
        reader,port=make_reader();coordinator=cm.DigitSCoordinator(Hass(),Entry(),reader)
        buttons={d.key:bm.DigitSButton(coordinator,Entry(),d) for d in bm.BUTTONS}
        assert buttons['capture_bus'].available and not buttons['stop_capture'].available
        await buttons['capture_bus'].async_press()
        assert not buttons['capture_bus'].available and buttons['stop_capture'].available
        await buttons['stop_capture'].async_press()
        await coordinator._capture_task
        assert not port.sent
        await coordinator.async_stop()
    asyncio.run(run())


def test_diagnostics_entry_hook_never_exports_config(ha_modules, make_reader):
    async def run():
        mod=importlib.import_module(f'{PKG}.diagnostics')
        hass=Hass();reader,_=make_reader()
        entry=Entry();entry.data={'connection':'socket://VERYSECRET@PRIVATE:1234'}
        hass.data={PKG:{entry.entry_id:SimpleNamespace(reader=reader)}}
        text=json.dumps(await mod.async_get_config_entry_diagnostics(hass,entry))
        assert 'VERYSECRET' not in text and 'PRIVATE' not in text and 'SECRET' not in text
        hass.data={}
        assert (await mod.async_get_config_entry_diagnostics(hass,entry))['status']=='integration_not_loaded'
    asyncio.run(run())


def test_manifest_translations_and_only_bounded_number_control():
    base=ROOT/'custom_components'/PKG
    manifest=json.loads((base/'manifest.json').read_text(encoding="utf-8"))
    assert manifest['version']=='0.7.1b1' and manifest['domain']==PKG
    assert manifest['requirements']==['serialx>=1.9.0,<2']
    en=json.loads((base/'strings.json').read_text(encoding="utf-8"))
    fi=json.loads((base/'translations/fi.json').read_text(encoding="utf-8"))
    assert 'lukukyselyitä' in fi['config']['step']['user']['description']
    assert 'never' in (base/'reader.py').read_text(encoding="utf-8").lower()
    assert not (base/'switch.py').exists()
    assert all((base/f'{name}.py').exists() for name in ('fan','select','binary_sensor','date'))
    assert (base/'number.py').exists()
    assert set(en['config'])==set(fi['config'])

