"""Temperature-step wire guards, true readback and failure paths."""
import importlib
import pytest
from conftest import Port, frame, reader_module, protocol, PKG

heat=importlib.import_module(f'{PKG}.heating_control')
control=importlib.import_module(f'{PKG}.speed_control')

class HeatPort(Port):
    def __init__(self, clock, responses, *, apply=True, reply=True, echo=False, **kwargs):
        super().__init__(clock, {**responses,0xA4:15}, echo=echo, **kwargs)
        self.apply=apply;self.reply=reply;self.changed=False
    def write(self,data,timeout=1):
        self.write_calls.append(bytes(data));count=min(len(data),self.partial)
        self.tx_buffer.extend(data[:count])
        if len(self.tx_buffer)==6:
            packet=bytes(self.tx_buffer);self.tx_buffer.clear();self.sent.append(packet)
            if self.echo:self.pending.extend(packet)
            if packet[3]==0:
                protocol.validate_read_request(packet)
                if not self.changed or self.reply:
                    self.pending.extend(frame(0x11,0x2E,packet[4],self.responses[packet[4]]))
            else:
                heat.validate_heating_packet(packet,protocol.FAN_SPEEDS[packet[4]])
                if packet[2]==0x11:
                    self.changed=True
                    if self.apply:self.responses[0xA4]=packet[4]
        return count

def active(clock,replies,**kwargs):
    port=HeatPort(clock,replies,**kwargs)
    r=reader_module.ActiveReader('private',lambda:port,clock=clock,wall_clock=clock.wall,control_enabled=True)
    r.sample();port.sent.clear()
    return r,port

@pytest.mark.parametrize('level',[1,2,3,5,6,7,8])
def test_steps_are_read_back_not_assumed(clock,replies,level):
    r,p=active(clock,replies,partial=2)
    result=r.set_heating_level(level)
    assert result['heating_level']==level
    assert [x for x in p.sent if x[3]!=0]==[heat.heating_packet(level,t) for t in (0x11,0x10,0x20)]
    assert result['heating_commands']==3
    assert 'vahvistettu' in result['heating_status']
    assert result['fan_speed']==5
    assert p.closed and not r._io_lock.locked()

def test_same_step_only_reads(clock,replies):
    r,p=active(clock,replies)
    r.set_heating_level(4)
    assert len(p.sent)==1 and p.sent[0][3]==0
    assert r.heating_commands==0

@pytest.mark.parametrize('value',[True,False,0,9,255,4.0,'4',None,4.5])
def test_invalid_steps_emit_nothing(clock,replies,value):
    r,p=active(clock,replies)
    with pytest.raises(control.SpeedControlError):r.set_heating_level(value)
    assert not p.sent

def test_nonapplied_command_never_retries(clock,replies):
    r,p=active(clock,replies,apply=False)
    with pytest.raises(control.SpeedControlError,match='kone ilmoittaa portaan 4'):r.set_heating_level(5)
    assert r.snapshot()['heating_level']==4
    assert len([x for x in p.sent if x[3]!=0])==3

def test_echo_is_not_confirmation(clock,replies):
    r,p=active(clock,replies,reply=False,echo=True)
    with pytest.raises(control.SpeedControlError,match='vastaus puuttuu'):r.set_heating_level(5)
    assert r.snapshot()['heating_level']==4

def test_preread_is_mandatory(clock,replies):
    r,p=active(clock,replies);p.changed=True;p.reply=False
    with pytest.raises(control.SpeedControlError,match='ei lähetetty'):r.set_heating_level(5)
    assert not [x for x in p.sent if x[3]!=0]

def test_capture_disabled_stopped_busy_stale(clock,replies):
    for reason in ['capture','disabled','stopped','busy','stale']:
        r,p=active(clock,replies)
        if reason=='capture':r.capture_active=True
        if reason=='disabled':r.control_enabled=False
        if reason=='stopped':r.stop()
        if reason=='busy':r._io_lock.acquire()
        if reason=='stale':clock.advance(181)
        with pytest.raises(control.SpeedControlError):r.set_heating_level(5)
        assert not p.sent

def test_packet_cannot_be_repurposed_as_any_other_register():
    for register in range(256):
        for raw in range(256):
            b=bytes((1,0x2E,0x11,register,raw));packet=b+bytes((sum(b)&255,))
            if register==0xA4 and raw==31:heat.validate_heating_packet(packet,5)
            else:
                with pytest.raises(control.SpeedControlError):heat.validate_heating_packet(packet,5)
    for target in range(256):
        if target not in heat.HEATING_RECIPIENTS:
            with pytest.raises(control.SpeedControlError):heat.heating_packet(5,target)

def test_poll_send_cannot_write_and_guards_cannot_cross(clock,replies):
    r,p=active(clock,replies)
    with pytest.raises(ValueError):r._send(p,heat.heating_packet(5,0x11))
    with pytest.raises(control.SpeedControlError):r._send(p,control.speed_packet(5,0x11),heating_level=5)
    with pytest.raises(control.SpeedControlError):r._send(p,heat.heating_packet(5,0x11),fan_level=5)
    with pytest.raises(control.SpeedControlError):r._send(p,heat.heating_packet(5,0x11),fan_level=5,heating_level=5)
    assert not p.sent

def test_new_profile_setup_only_reads(clock,replies):
    r,p=active(clock,replies)
    assert r.heating_commands==0 and r.control_commands==0
    assert r.snapshot()['heating_level']==4

def test_shared_cooldown(clock,replies):
    r,p=active(clock,replies);r.set_heating_level(5);count=len(p.sent)
    with pytest.raises(control.SpeedControlError,match='kolme sekuntia'):r.set_heating_level(4)
    assert len(p.sent)==count
    clock.advance(3);assert r.set_heating_level(4)['heating_level']==4

def test_missing_optional_target_does_not_break_measurements(clock,replies):
    p=Port(clock,replies);r=reader_module.ActiveReader('private',lambda:p,clock=clock,wall_clock=clock.wall,control_enabled=True)
    data=r.sample()
    assert data['connection_state']=='Yhteys toimii'
    assert data.get('heating_level') is None
    assert r.optional_read_errors=={'0xA4':'no_response'}
    assert r.control_commands==0 and r.heating_commands==0

def test_hardware_capture_matches_exact_masks():
    from pathlib import Path
    import json
    capture=json.loads((Path(__file__).parent/'fixtures'/'temperature-command-sequence.json').read_text(encoding='utf-8'))
    actual=[x for x in capture if x['sender']=='0x21' and x['register']=='0xA4']
    assert [(int(x['recipient'],16),x['raw_value']) for x in actual]==[(0x11,31),(0x10,31),(0x20,31),(0x11,15),(0x10,15),(0x20,15)]
    # Outgoing source must remain our 0x2E identity, not impersonate panel 0x21.
    for record in actual:
        level=protocol.FAN_SPEEDS[record['raw_value']]
        expected=heat.heating_packet(level,int(record['recipient'],16))
        assert expected[1]==0x2E and expected[3:5]==bytes((0xA4,record['raw_value']))
