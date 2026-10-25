import json
import pytest
from conftest import Clock, Port, frame, reader_module as r, protocol as p


def test_full_success_preserves_observed_measurements(make_reader):
    reader, port = make_reader(echo=True)
    data = reader.sample()
    assert data['read_requests'] == data['read_responses'] == 7
    assert data['read_timeouts'] == data['invalid_values'] == 0
    assert data['fan_speed'] == 5
    assert data['temperature_outdoor_air'] == 13
    assert data['temperature_supply_air'] == 19
    assert data['temperature_extract_air'] == 21
    assert data['temperature_exhaust_air'] == 16
    assert data['supply_temperature_gain'] == 6
    assert data['exhaust_temperature_drop'] == 5
    assert data['temperature_recovery_efficiency'] == 75.0
    assert data['register_a9_raw'] == data['register_a5_raw'] == 15
    assert 'basic_fan_speed' not in data and 'maximum_fan_speed' not in data
    assert data['connection_state'] == 'Yhteys toimii'
    assert port.closed and len(port.sent) == 7
    assert all(packet[3] == 0 for packet in port.sent)


def test_actual_fan_changes_but_remote_request_is_not_actual_state(make_reader):
    reader, port = make_reader()
    reader.sample()
    port.responses[0x29] = 0x3F
    data = reader.sample()
    assert data['fan_speed'] == 6 and data['previous_fan_speed'] == 5
    assert data['fan_speed_changes'] == 1
    reader._ingest(frame(0x21,0x11,0x29,0x7F))
    data = reader.snapshot()
    assert data['fan_speed'] == 6 and data['last_remote_fan_speed'] == 7
    assert data['last_remote_fan_sender'] == '0x21'
    assert data['fan_speed_changes'] == 1
    reader._ingest(frame(0x11,0x20,0x29,0x7F))
    assert reader.snapshot()['fan_speed'] == 7
    assert reader.snapshot()['fan_speed_changes'] == 2


def test_wrong_mainboard_never_updates_measurement(make_reader):
    reader, _ = make_reader()
    reader._ingest(frame(0x12,0x2E,0x29,0x7F))
    assert 'fan_speed' not in reader.snapshot()
    assert reader.snapshot()['received_frames'] == 1


def test_partial_writes_are_completed(make_reader):
    reader, port = make_reader(partial=2)
    assert reader.sample()['read_responses'] == 7
    assert len(port.sent) == 7 and len(port.write_calls) == 21


def test_zero_length_write_fails_instead_of_busy_loop(make_reader):
    reader, port = make_reader(partial=0)
    data = reader.sample()
    assert 'TimeoutError' in data['last_error'] and port.closed
    assert data['read_requests'] == 0


@pytest.mark.parametrize('failure', ['open','read','write','close'])
def test_transport_errors_redacted_and_port_closed(make_reader, failure):
    reader, port = make_reader(fail=failure)
    data = reader.sample()
    assert data['last_error'] != 'Ei virheitä' and port.closed
    assert 'SECRET' not in json.dumps(reader.diagnostics())


def test_factory_failure_is_caught(clock):
    def fail(): raise RuntimeError('socket://SECRET@private')
    reader = r.ActiveReader('socket://SECRET@private', fail, clock=clock, wall_clock=clock.wall)
    assert reader.sample()['last_error'] == 'transport: RuntimeError'
    assert 'SECRET' not in json.dumps(reader.diagnostics())


def test_failed_first_register_not_erased_by_later_successes(make_reader, replies):
    values = dict(replies); del values[0x58]
    reader, _ = make_reader(values)
    data = reader.sample()
    assert data['read_responses'] == 6
    assert data['read_timeouts'] == 2
    assert data['last_error'] == '0x58: no_response'
    assert data['connection_state'] == 'Osittaiset lukutiedot'
    assert 'temperature_recovery_efficiency' not in data


def test_all_timeouts_show_failure(make_reader):
    reader, _ = make_reader({})
    data = reader.sample()
    assert data['read_requests'] == 14 and data['read_timeouts'] == 14
    assert data['read_responses'] == 0
    assert data['connection_state'] == 'Ei tuoreita mittauksia'
    assert data['last_error'] != 'Ei virheitä'


def test_invalid_temperature_not_cached_as_valid(make_reader, replies):
    values=dict(replies); values[0x58]=0
    reader, _=make_reader(values)
    data=reader.sample()
    assert data['invalid_values'] == 1
    assert 'temperature_outdoor_air' not in data
    assert data['last_error'] == '0x58: invalid_value'


def test_live_age_and_staleness_without_wire_io(make_reader, clock):
    reader, port=make_reader()
    reader.sample()
    clock.advance(65)
    assert reader.snapshot()['last_success_age'] >= 65
    assert len(port.sent) == 7
    clock.advance(181)
    data=reader.snapshot()
    assert 'fan_speed' not in data and 'temperature_outdoor_air' not in data
    assert 'temperature_recovery_efficiency' not in data
    assert data['connection_state'] == 'Ei tuoreita mittauksia'


def test_derived_values_require_coherent_timestamps(make_reader, clock):
    reader, _=make_reader()
    reader.sample()
    clock.advance(60)
    reader._ingest(frame(0x11,0x20,0x58,p.NTC5K.index(10)))
    data=reader.snapshot()
    assert 'supply_temperature_gain' not in data
    assert 'temperature_recovery_efficiency' not in data
    assert data['exhaust_temperature_drop'] == 5


def test_unsupported_tx_blocked_at_final_boundary(make_reader):
    reader, port=make_reader()
    with pytest.raises(ValueError):reader._send(port,frame(0x2E,0x11,0x29,0x7F))
    assert not port.write_calls
    assert reader.snapshot()['blocked_transmissions'] == 1


def test_bus_traffic_is_parsed_during_quiet_wait(make_reader):
    reader, _=make_reader(incoming=frame(0x21,0x20,0x29,0x3F))
    data=reader.sample()
    assert data['last_remote_fan_speed'] == 6
    assert data['fan_speed'] == 5


def test_busy_bus_does_not_transmit(clock, replies):
    port=Port(clock,replies)
    def continuously_busy():
        if not port.pending: port.pending.extend(frame(0x21,0x20,0x29,0x3F))
    port.on_read=continuously_busy
    reader=r.ActiveReader('fake',lambda:port,clock=clock,wall_clock=clock.wall)
    data=reader.sample()
    assert not port.sent and not port.write_calls
    assert data['bus_busy'] == 14
    assert data['last_error'] != 'Ei virheitä'


def test_capture_never_transmits_and_retains_unknown_frames(make_reader):
    raw=frame(0x21,0x11,0x77,0x22)+frame(0x21,0x11,0x29,0x3F)+frame(0x11,0x20,0x29,0x3F)
    reader, port=make_reader(incoming=raw)
    reader.prepare_capture()
    data=reader.capture(2)
    assert data['capture_status'] == 'Tallennus valmis' and not data['capture_active']
    assert port.closed and not port.write_calls
    assert data['read_requests'] == 0 and data['fan_speed'] == 6
    capture=reader.diagnostics()['passive_capture']
    assert capture['received_frames'] == 3
    assert capture['frames'][0]['register'] == '0x77'
    reader.sample()
    assert len(reader.diagnostics()['passive_capture']['frames']) == 3


def test_capture_cancel_before_open_returns_final_status(make_reader):
    reader, port=make_reader()
    reader.prepare_capture(); reader.cancel_capture()
    result=reader.capture(2)
    assert not result['capture_active'] and result['capture_status'] == 'Tallennus keskeytetty'
    assert not port.opened and not port.sent


def test_capture_cancel_during_read_closes_port(make_reader):
    reader, port=make_reader()
    port.on_read=reader.cancel_capture
    reader.prepare_capture()
    data=reader.capture(120)
    assert data['capture_status'] == 'Tallennus keskeytetty'
    assert port.closed and not port.sent


def test_capture_ring_is_bounded_and_reports_lost_frames(make_reader):
    reader, port=make_reader(incoming=frame(0x21,0x20,0x29,0x3F)*(r.CAPTURE_LIMIT+5))
    reader.prepare_capture(); reader.capture(60)
    diagnostics=reader.diagnostics()
    capture=diagnostics['passive_capture']
    assert len(capture['frames']) == r.CAPTURE_LIMIT
    assert capture['dropped_frames'] == 5
    assert len(diagnostics['recent_frames']) == r.TRACE_LIMIT
    assert len(bytes.fromhex(diagnostics['recent_rx_bytes_hex'])) <= 128
    assert not port.sent


def test_stopped_reader_cannot_poll_or_capture(make_reader):
    reader, port=make_reader()
    reader.stop()
    assert reader.sample()['read_requests'] == 0
    with pytest.raises(RuntimeError): reader.prepare_capture()
    assert not port.sent


def test_diagnostics_json_has_no_url_credentials_or_config_data(make_reader):
    reader, _=make_reader()
    reader.sample()
    data=reader.diagnostics()
    text=json.dumps(data)
    assert data['transport_type'] == 'socket'
    assert 'SECRET' not in text and 'private' not in text and 'username' not in text
    assert data['settings_writes_supported'] is False
    assert data['latest_raw_registers']['0xA9']['raw_hex'] == '0x0F'
    assert all(f['direction']=='tx' or f['direction']=='rx' for f in data['recent_frames'])


def test_capture_and_poll_never_open_two_connections(make_reader):
    import threading
    reader, port = make_reader()
    entered, release = threading.Event(), threading.Event()
    def block_read():
        entered.set()
        assert release.wait(2)
    port.on_read = block_read
    reader.prepare_capture()
    worker = threading.Thread(target=reader.capture, args=(2,))
    worker.start()
    try:
        assert entered.wait(2)
        data = reader.sample()
        assert data['capture_active'] and not port.sent
        reader.stop()
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert port.closed and not port.sent


def test_wait_closed_joins_real_io_worker(make_reader):
    import threading
    reader, port = make_reader()
    entered, release, joined = threading.Event(), threading.Event(), threading.Event()
    def block_read():
        entered.set()
        assert release.wait(2)
    port.on_read = block_read
    worker = threading.Thread(target=reader.sample)
    worker.start()
    try:
        assert entered.wait(2)
        reader.stop()
        waiter = threading.Thread(target=lambda: (reader.wait_closed(), joined.set()))
        waiter.start()
        assert not joined.wait(0.02)
    finally:
        release.set()
        worker.join(2)
        waiter.join(2)
    assert joined.is_set() and port.closed
    assert not port.sent


def test_serialx_connection_parameters_preserved(monkeypatch, clock):
    import sys
    import types
    calls=[]
    fake=types.SimpleNamespace(PARITY_NONE='N', STOPBITS_ONE=1, EIGHTBITS=8,
        serial_for_url=lambda *args,**kwargs:calls.append((args,kwargs)) or object())
    monkeypatch.setitem(sys.modules,'serialx',fake)
    reader=r.ActiveReader('esphome-hass://same-existing-connection',clock=clock)
    reader._make_port()
    args,kw=calls[0]
    assert args==('esphome-hass://same-existing-connection',)
    assert kw==dict(baudrate=9600,parity='N',stopbits=1,byte_size=8,
                   read_timeout=1.0,write_timeout=1.0,connect_timeout=1.0)
