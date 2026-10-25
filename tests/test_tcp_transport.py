"""Exercise the real serialx TCP transport against a local simulated unit."""
from contextlib import contextmanager
import socketserver
import threading

import pytest

from conftest import frame, protocol, reader_module


@contextmanager
def unit():
    packets = []
    values = {0x58: protocol.NTC5K.index(12), 0x5B: protocol.NTC5K.index(18),
              0x5A: protocol.NTC5K.index(20), 0x5C: protocol.NTC5K.index(16),
              0x29: 63, 0xA9: 15, 0xA5: 15, 0xA4: 15}

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            parser = protocol.FrameParser()
            while data := self.request.recv(1024):
                for packet in parser.feed(data):
                    packets.append(packet)
                    if packet.is_query:
                        self.request.sendall(frame(0x11, 0x2E, packet.raw, values[packet.raw]))
                    elif packet.recipient == 0x11:
                        values[packet.register] = packet.raw

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        worker.start()
        try:
            yield f"socket://127.0.0.1:{server.server_address[1]}", packets
        finally:
            server.shutdown()
            worker.join(timeout=5)
            assert not worker.is_alive()


def test_real_socket_poll_and_confirmed_controls():
    pytest.importorskip("serialx")
    with unit() as (url, packets):
        reader = reader_module.ActiveReader(url, control_enabled=True)
        state = reader.sample()
        assert state["connection_state"] == "Yhteys toimii"
        assert state["fan_speed"] == 6 and state["heating_level"] == 4
        assert state["temperature_supply_air"] == 18
        assert len(packets) == 8 and all(p.is_query for p in packets)
        assert reader.set_fan_speed(7)["fan_speed"] == 7
        writes = [p for p in packets if not p.is_query]
        assert [(p.register, p.recipient, p.raw) for p in writes] == [(0x29, 0x11, 127), (0x29, 0x20, 127)]
        reader.stop()
        reader.wait_closed()


def test_real_socket_passive_capture_transmits_nothing():
    pytest.importorskip("serialx")
    with unit() as (url, packets):
        reader = reader_module.ActiveReader(url)
        reader.prepare_capture()
        result = reader.capture(1)
        assert result["capture_status"] == "Tallennus valmis"
        assert packets == []
        reader.stop()
