"""Legacy Vallox Digit S passive telegram decoder.

Based on public GPL-3.0 Helios/Vallox and older pvainio/vallox-rs485
protocol implementations. No telegram construction, bus writing or polling.
The NTC5k LUT is adapted from the Helios/Vallox GPL-3.0 project.
"""
from dataclasses import dataclass
from collections import deque

# NTC5K lookup table, raw byte 0x00..0xff -> deg C
NTC5K = (
    -74,-70,-66,-62,-59,-56,-54,-52,-50,-48,-47,-46,-44,-43,-42,-41,-40,-39,-38,-37,-36,
    -35,-34,-33,-33,-32,-31,-30,-30,-29,-28,-28,-27,-27,-26,-25,-25,-24,-24,-23,-23,-22,
    -22,-21,-21,-20,-20,-19,-19,-19,-18,-18,-17,-17,-16,-16,-16,-15,-15,-14,-14,-14,-13,
    -13,-12,-12,-12,-11,-11,-11,-10,-10,-9,-9,-9,-8,-8,-8,-7,-7,-7,-6,-6,-6,-5,-5,-5,-4,
    -4,-4,-3,-3,-3,-2,-2,-2,-1,-1,-1,-1,0,0,0,1,1,1,2,2,2,3,3,3,4,4,4,5,5,5,5,6,6,6,7,7,
    7,8,8,8,9,9,9,10,10,10,11,11,11,12,12,12,13,13,13,14,14,14,15,15,15,16,16,16,17,17,
    18,18,18,19,19,19,20,20,21,21,21,22,22,22,23,23,24,24,24,25,25,26,26,27,27,27,28,28,
    29,29,30,30,31,31,32,32,33,33,34,34,35,35,36,36,37,37,38,38,39,40,40,41,41,42,43,43,
    44,45,45,46,47,48,48,49,50,51,52,53,53,54,55,56,57,59,60,61,62,63,65,66,68,69,71,73,
    75,77,79,81,82,86,90,93,97,100,100,100,100,100,100,100,100,100
)
assert len(NTC5K) == 256, len(NTC5K)

# Legacy 2001 LED remote register map, not assumed validated for all Digit S.
REGISTERS = {
    0x58: "temperature_outdoor_air",
    0x5B: "temperature_supply_air",
    0x5A: "temperature_extract_air",
    0x5C: "temperature_exhaust_air",
    0x29: "fan_speed",
}
FAN_SPEEDS = {1: 1, 3: 2, 7: 3, 15: 4, 31: 5, 63: 6, 127: 7, 255: 8}
# Deliberately broad ranges; absurd/sentinel values do not become temperatures.
TEMPERATURE_LIMITS = {
    "temperature_outdoor_air": (-55, 65),
    "temperature_supply_air": (-30, 75),
    "temperature_extract_air": (-20, 75),
    "temperature_exhaust_air": (-55, 75),
}

@dataclass(frozen=True)
class Telegram:
    sender: int
    recipient: int
    register: int
    raw: int


def decode(data: bytes) -> Telegram | None:
    """Validate classic Vallox 6-byte telegram; reject read requests."""
    if len(data) != 6 or data[0] != 0x01:
        return None
    if sum(data[:5]) & 0xFF != data[5]:
        return None
    if data[3] == 0:
        return None  # register query, not a measurement
    return Telegram(data[1], data[2], data[3], data[4])


class StreamParser:
    """Resynchronize corrupted/delimited serial byte stream safely."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[Telegram]:
        self.buffer.extend(data)
        decoded = []
        while len(self.buffer) >= 6:
            if self.buffer[0] != 0x01:
                del self.buffer[0]
                continue
            candidate = decode(bytes(self.buffer[:6]))
            if candidate is None:
                del self.buffer[0]
                continue
            decoded.append(candidate)
            del self.buffer[:6]
        return decoded


def classify(telegram: Telegram) -> tuple[str, int | float] | None:
    """Only accept mainboard-originated data, never infer from unknown registers."""
    if telegram.sender != 0x11 or not 0x20 <= telegram.recipient <= 0x2F:
        return None
    name = REGISTERS.get(telegram.register)
    if name is None:
        return None
    if name == "fan_speed":
        speed = FAN_SPEEDS.get(telegram.raw)
        return (name, speed) if speed is not None else None
    temp = NTC5K[telegram.raw]
    lo, hi = TEMPERATURE_LIMITS[name]
    if telegram.raw == 0 or not lo <= temp <= hi:
        return None
    return (name, temp)
