"""Old LED-panel target-temperature steps, separate from measured air temperature.

Hardware capture 2026-10-23: physical panel 0x21 sends A4=1F (step 5),
then A4=0F (step 4) to 11, 10, 20. Mainboard responds in the capture.
The eight-LED cumulative mask is used without interpolating unknown degrees.
Owner confirms anchors: step 1=10 C, step 5=20 C, step 8=27 C.
No heater-enable, relay-duty, frost-protection or register 06 writes.
"""
from .speed_control import SpeedControlError
MIN_HEATING_LEVEL = 1
MAX_HEATING_LEVEL = 8
HEATING_REGISTER = 0xA4
HEATING_RECIPIENTS = (0x11, 0x10, 0x20)
CONFIRMED_TEMPERATURE_ANCHORS = {1: 10, 5: 20, 8: 27}

def validate_heating_level(level):
    if type(level) is not int or not MIN_HEATING_LEVEL <= level <= MAX_HEATING_LEVEL:
        raise SpeedControlError("Valitse lämpötilaporras väliltä 1–8.")

def heating_packet(level, recipient):
    validate_heating_level(level)
    if type(recipient) is not int or recipient not in HEATING_RECIPIENTS:
        raise SpeedControlError("Lämpötilakomennon vastaanottaja ei ole sallittu.")
    data = bytes((1, 0x2E, recipient, HEATING_REGISTER, (1 << level) - 1))
    return data + bytes((sum(data) & 255,))

def validate_heating_packet(packet, level):
    validate_heating_level(level)
    if len(packet) != 6 or packet[2] not in HEATING_RECIPIENTS:
        raise SpeedControlError("Virheellinen lämpötilakomento estettiin.")
    if packet != heating_packet(level, packet[2]):
        raise SpeedControlError("Virheellinen lämpötilakomento estettiin.")
