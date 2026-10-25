"""Protocol and failure-path tests. These do not claim physical validation."""
import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace
import pytest
from conftest import Port, frame, reader_module, protocol, PKG
from test_ha_boundary import ha_modules, Hass, Entry

control = importlib.import_module(f"{PKG}.speed_control")


class ControlPort(Port):
    def __init__(self, clock, replies, *, apply=True, reply=True, echo=False, **kwargs):
        super().__init__(clock, {**replies, 0x29: 0x3F}, echo=echo, **kwargs)
        self.apply, self.reply, self.changed = apply, reply, False

    def write(self, data, timeout=1):
        if self.fail == "write":
            raise OSError("socket://user:SECRET@private")
        self.write_calls.append(bytes(data))
        count = min(len(data), self.partial)
        self.tx_buffer.extend(data[:count])
        if len(self.tx_buffer) == 6:
            packet = bytes(self.tx_buffer)
            self.tx_buffer.clear()
            self.sent.append(packet)
            if self.echo:
                self.pending.extend(packet)
            if packet[3] == 0:
                protocol.validate_read_request(packet)
                if not self.changed or self.reply:
                    self.pending.extend(frame(0x11, 0x2E, packet[4], self.responses[packet[4]]))
            else:
                control.validate_speed_packet(packet, protocol.FAN_SPEEDS[packet[4]])
                if packet[2] == 0x11:
                    self.changed = True
                    if self.apply:
                        self.responses[0x29] = packet[4]
        return count


def live_reader(clock, replies, **kwargs):
    port = ControlPort(clock, replies, **kwargs)
    r = reader_module.ActiveReader("private", lambda: port, clock=clock,
                                   wall_clock=clock.wall, control_enabled=True)
    r.sample()
    port.sent.clear()
    return r, port


@pytest.mark.parametrize("level", [5, 7, 8])
def test_manual_command_and_real_readback(clock, replies, level):
    r, port = live_reader(clock, replies, partial=2)
    result = r.set_fan_speed(level)
    writes = [p for p in port.sent if p[3] != 0]
    assert writes == [control.speed_packet(level, 0x11), control.speed_packet(level, 0x20)]
    assert result['fan_speed'] == level
    assert result['control_commands'] == 2
    assert 'vahvistettu' in result['control_status']
    assert port.closed and not r._io_lock.locked()


def test_same_value_does_not_write(clock, replies):
    r, port = live_reader(clock, replies)
    assert r.set_fan_speed(6)['fan_speed'] == 6
    assert len(port.sent) == 1 and port.sent[0][3] == 0
    assert r.control_commands == 0


@pytest.mark.parametrize("level", [True, False, 0, 1, 4, 9, 255, 6.0, 5.5, "6", None])
def test_bad_values_never_reach_wire(clock, replies, level):
    r, port = live_reader(clock, replies)
    with pytest.raises(control.SpeedControlError):
        r.set_fan_speed(level)
    assert not port.sent


def test_no_optimistic_state_or_write_retries(clock, replies):
    r, port = live_reader(clock, replies, apply=False)
    with pytest.raises(control.SpeedControlError, match='kone ilmoittaa tason 6'):
        r.set_fan_speed(5)
    assert r.snapshot()['fan_speed'] == 6
    assert len([p for p in port.sent if p[3] != 0]) == 2


def test_echo_is_not_mainboard_readback(clock, replies):
    r, port = live_reader(clock, replies, reply=False, echo=True)
    with pytest.raises(control.SpeedControlError, match='vastaus puuttuu'):
        r.set_fan_speed(5)
    assert r.snapshot()['fan_speed'] == 6
    assert len([p for p in port.sent if p[3] != 0]) == 2


def test_no_command_without_fresh_preread(clock, replies):
    r, port = live_reader(clock, replies)
    port.changed, port.reply = True, False
    with pytest.raises(control.SpeedControlError, match='komentoa ei lähetetty'):
        r.set_fan_speed(5)
    assert not any(p[3] != 0 for p in port.sent)


def test_capture_stop_busy_and_stale_block_commands(clock, replies):
    for reason in ['capture', 'stop', 'busy', 'stale', 'disabled']:
        r, port = live_reader(clock, replies)
        if reason == 'capture': r.capture_active = True
        if reason == 'stop': r.stop()
        if reason == 'busy': r._io_lock.acquire()
        if reason == 'stale': clock.advance(181)
        if reason == 'disabled': r.control_enabled = False
        with pytest.raises(control.SpeedControlError): r.set_fan_speed(5)
        assert not port.sent


def test_cooldown_prevents_repeat_commands(clock, replies):
    r, port = live_reader(clock, replies)
    r.set_fan_speed(5)
    count = len(port.sent)
    with pytest.raises(control.SpeedControlError, match='kolme sekuntia'):
        r.set_fan_speed(6)
    assert len(port.sent) == count
    clock.advance(3)
    assert r.set_fan_speed(6)['fan_speed'] == 6


def test_credentials_not_exposed_on_control_failure(clock, replies):
    r, port = live_reader(clock, replies)
    port.fail = 'open'
    with pytest.raises(control.SpeedControlError) as caught: r.set_fan_speed(5)
    assert 'SECRET' not in str(caught.value)
    assert 'SECRET' not in r.control_status
    assert port.closed and not r._io_lock.locked()


def test_all_arbitrary_registers_and_values_are_blocked():
    for register in range(256):
        for raw in range(256):
            b = bytes((1, 0x2E, 0x11, register, raw))
            packet = b + bytes((sum(b) & 255,))
            if register == 0x29 and raw == 0x1F:
                control.validate_speed_packet(packet, 5)
            else:
                with pytest.raises(control.SpeedControlError):
                    control.validate_speed_packet(packet, 5)
    for target in range(256):
        if target not in (0x11, 0x20):
            with pytest.raises(control.SpeedControlError): control.speed_packet(5, target)


def test_polling_tx_cannot_be_used_to_write(clock, replies):
    r, port = live_reader(clock, replies)
    with pytest.raises(ValueError): r._send(port, control.speed_packet(5, 0x11))
    assert not port.sent


def test_coordinator_updates_state_even_on_control_failure(ha_modules, clock, replies):
    async def run():
        mod = importlib.import_module(f'{PKG}.coordinator')
        r, port = live_reader(clock, replies, apply=False)
        c = mod.DigitSCoordinator(Hass(), Entry(), r)
        with pytest.raises(control.SpeedControlError): await c.async_set_fan_speed(5)
        assert c.data['fan_speed'] == 6 and not c._wire_lock.locked()
        await c._wire_lock.acquire()
        count = len(port.sent)
        with pytest.raises(control.SpeedControlError): await c.async_set_fan_speed(5)
        assert len(port.sent) == count
        c._wire_lock.release()
    asyncio.run(run())


def test_number_uses_actual_state_and_validates_inputs(ha_modules, monkeypatch, clock, replies):
    module = ModuleType('homeassistant.components.number')
    module.NumberEntity = type('NumberEntity', (), {})
    module.NumberMode = SimpleNamespace(BOX='box')
    monkeypatch.setitem(sys.modules, module.__name__, module)
    errors = ModuleType('homeassistant.exceptions')
    errors.HomeAssistantError = type('HomeAssistantError', (Exception,), {})
    monkeypatch.setitem(sys.modules, errors.__name__, errors)
    monkeypatch.delitem(sys.modules, f'{PKG}.number', raising=False)
    nmod = importlib.import_module(f'{PKG}.number')
    cmod = importlib.import_module(f'{PKG}.coordinator')
    async def run():
        r, port = live_reader(clock, replies)
        c = cmod.DigitSCoordinator(Hass(), Entry(), r)
        c.data = r.snapshot()
        n = nmod.DigitSSpeed(c, Entry())
        assert n.native_value == 6 and n.available
        for bad in [4, 9, 5.5, True, None, float('nan'), float('inf')]:
            with pytest.raises(errors.HomeAssistantError): await n.async_set_native_value(bad)
        assert not port.sent
        await n.async_set_native_value(5.0)
        assert n.native_value == 5
        c._stopping = True
        assert not n.available
    asyncio.run(run())
