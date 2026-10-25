"""Narrow manual speed command for this hardware profile, never settings scans.

Reference: pvainio/vallox-rs485 SetSpeed, tested on the old LED generation.
All eight device levels are supported. Installation limits belong to the caller.
Do not infer limits from A9/A5, and never write them or register 06.
"""
MIN_SPEED = 1
MAX_SPEED = 8
COOLDOWN_SECONDS = 3.0
SPEED_REGISTER = 0x29
REMOTE_MULTICAST = 0x20


class SpeedControlError(Exception):
    """Only deliberately constructed, credential-free messages reach HA."""


def validate_speed(level):
    if type(level) is not int or not MIN_SPEED <= level <= MAX_SPEED:
        raise SpeedControlError("Valitse kokonaisluku väliltä 1–8.")


def speed_packet(level, recipient):
    validate_speed(level)
    if type(recipient) is not int or recipient not in (0x11, REMOTE_MULTICAST):
        raise SpeedControlError("Nopeuskomennon vastaanottaja ei ole sallittu.")
    data = bytes((1, 0x2E, recipient, SPEED_REGISTER, (1 << level) - 1))
    return data + bytes((sum(data) & 255,))


def validate_speed_packet(packet, level):
    validate_speed(level)
    if len(packet) != 6 or packet[2] not in (0x11, REMOTE_MULTICAST):
        raise SpeedControlError("Virheellinen nopeuskomento estettiin.")
    if packet != speed_packet(level, packet[2]):
        raise SpeedControlError("Virheellinen nopeuskomento estettiin.")
