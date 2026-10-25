"""Offline fixtures. Protocol tests do not require Home Assistant installed."""
import importlib
from pathlib import Path
import sys
import types
import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = "vallox_digit_s_legacy"
package = types.ModuleType(PKG)
package.__path__ = [str(ROOT / "custom_components" / PKG)]
sys.modules[PKG] = package
protocol = importlib.import_module(f"{PKG}.protocol")
reader_module = importlib.import_module(f"{PKG}.reader")


def frame(sender, recipient, register, value):
    data = bytes((1, sender, recipient, register, value))
    return data + bytes((sum(data) & 255,))


class Clock:
    def __init__(self): self.now = 10.0
    def __call__(self): return self.now
    def advance(self, dt): self.now += max(0.00001, dt)
    def wall(self): return 1792666800.0 + self.now


class Port:
    def __init__(self, clock, responses=None, incoming=b"", *, partial=6, fail=None, echo=False):
        self.clock, self.responses = clock, responses or {}
        self.pending = bytearray(incoming)
        self.tx_buffer = bytearray()
        self.sent = []
        self.write_calls = []
        self.partial, self.fail, self.echo = partial, fail, echo
        self.opened, self.closed = False, False
        self.on_read = None
    def open(self):
        if self.fail == "open": raise OSError("socket://username:SECRET@private:1234")
        self.opened = True
    def close(self):
        self.closed = True
        self.opened = False
        if self.fail == "close": raise OSError("SECRET")
    def readinto(self, buffer, timeout=0):
        if self.fail == "read": raise OSError("SECRET")
        if self.on_read: self.on_read()
        if self.pending:
            self.clock.advance(0.001)
            buffer[0] = self.pending.pop(0)
            return 1
        self.clock.advance(timeout)
        return 0
    def write(self, data, timeout=1):
        if self.fail == "write": raise OSError("SECRET")
        self.write_calls.append(bytes(data))
        count = min(len(data), self.partial)
        self.tx_buffer.extend(data[:count])
        if len(self.tx_buffer) == 6:
            packet = bytes(self.tx_buffer)
            protocol.validate_read_request(packet)
            self.sent.append(packet)
            self.tx_buffer.clear()
            if self.echo: self.pending.extend(packet)
            if packet[4] in self.responses:
                self.pending.extend(frame(0x11, 0x2E, packet[4], self.responses[packet[4]]))
        return count


@pytest.fixture
def clock(): return Clock()


@pytest.fixture
def replies():
    ntc = protocol.NTC5K
    return {0x58: ntc.index(13), 0x5B: ntc.index(19), 0x5A: ntc.index(21),
            0x5C: ntc.index(16), 0x29: 0x1F, 0xA9: 0x0F, 0xA5: 0x0F}


@pytest.fixture
def make_reader(clock, replies):
    def make(responses=None, **kwargs):
        port = Port(clock, replies if responses is None else responses, **kwargs)
        reader = reader_module.ActiveReader(
            "socket://username:SECRET@private:1234", lambda: port,
            clock=clock, wall_clock=clock.wall,
        )
        return reader, port
    return make
