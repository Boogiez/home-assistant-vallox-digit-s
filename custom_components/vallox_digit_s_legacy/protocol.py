"""DIGIT framing, strictly read-only TX and the hardware-verified legacy map.

2011 Vallox protocol, sections 2 and 3: 9600/8N1, six bytes, additive checksum.
The old LED-controller temperature addresses are NOT those in the 2011 table.
A9/A5 semantics have not been validated on the user's Digit S; expose raw only.
"""
from __future__ import annotations
from dataclasses import dataclass
from .legacy_protocol import FAN_SPEEDS, NTC5K, TEMPERATURE_LIMITS

SENDER = 0x2E
MAINBOARD = 0x11
CORE_REGISTERS = {
    0x58: "temperature_outdoor_air",
    0x5B: "temperature_supply_air",
    0x5A: "temperature_extract_air",
    0x5C: "temperature_exhaust_air",
    0x29: "fan_speed",
}
RAW_REGISTERS = {0xA9: "register_a9_raw", 0xA5: "register_a5_raw"}
OPTIONAL_REGISTERS = {0xA4: "heating_level"}
REGISTERS = {**CORE_REGISTERS, **RAW_REGISTERS, **OPTIONAL_REGISTERS}


def read_request(register: int) -> bytes:
    """Only the fixed measurement registers and captured A4 target are allowed. No register scan."""
    if type(register) is not int or register not in REGISTERS:
        raise ValueError("Register is not allowed for Digit S polling")
    payload = bytes((1, SENDER, MAINBOARD, 0, register))
    return payload + bytes((sum(payload) & 255,))


def validate_read_request(packet: bytes) -> None:
    """Defense at the final TX boundary, not just in the packet constructor.

    Reject control writes, arbitrary senders/recipients, ACKs and extra bytes.
    Register 06 and bus-control registers 8F/91 cannot be sent in any form.
    """
    if len(packet) != 6 or packet[4] not in REGISTERS:
        raise ValueError("Only complete whitelisted read requests may be transmitted")
    if packet != read_request(packet[4]):
        raise ValueError("A setting write or malformed packet was blocked")


def convert(register: int, raw: int) -> int | None:
    if type(raw) is not int or not 0 <= raw <= 255:
        return None
    if register in RAW_REGISTERS:
        return raw  # no FAN_SPEEDS conversion, no guessed +1 offset
    if register in (0x29, 0xA4):
        return FAN_SPEEDS.get(raw)
    key = CORE_REGISTERS.get(register)
    if key is None or raw == 0:
        return None
    value = NTC5K[raw]
    low, high = TEMPERATURE_LIMITS[key]
    return value if low <= value <= high else None


@dataclass(frozen=True)
class Frame:
    sender: int
    recipient: int
    register: int
    raw: int
    packet: bytes

    @property
    def is_query(self) -> bool:
        return self.register == 0


def decode_frame(packet: bytes) -> Frame | None:
    """Decode both queries and value frames. A single-byte ACK is not a frame."""
    if len(packet) != 6 or packet[0] != 1:
        return None
    if (sum(packet[:5]) & 255) != packet[5]:
        return None
    return Frame(packet[1], packet[2], packet[3], packet[4], packet)


class FrameParser:
    """Bounded sliding parser; tolerate fragmented frames, noise and echoes."""
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.checksum_errors = 0
        self.discarded_bytes = 0

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        frames = []
        while len(self.buffer) >= 6:
            if self.buffer[0] != 1:
                del self.buffer[0]
                self.discarded_bytes += 1
                continue
            frame = decode_frame(bytes(self.buffer[:6]))
            if frame is None:
                del self.buffer[0]
                self.checksum_errors += 1
                self.discarded_bytes += 1
                continue
            frames.append(frame)
            del self.buffer[:6]
        return frames
