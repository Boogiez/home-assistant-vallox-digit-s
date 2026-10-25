# Supported protocol

This driver targets the older Digit S LED controller. Newer Digit SE and MV
features cannot be assumed to use the same registers.

| Feature | Register | Support |
|---|---|---|
| Outdoor temperature | `0x58` | Read, legacy NTC table |
| Supply temperature | `0x5B` | Read, legacy NTC table |
| Extract temperature | `0x5A` | Read, legacy NTC table |
| Exhaust temperature | `0x5C` | Read, legacy NTC table |
| Fan level | `0x29` | Read 1–8; write 5–8 with mainboard readback |
| Supply-air temperature request | `0xA4` | Optional read; write eight LED steps with readback |
| Unidentified settings | `0xA9`, `0xA5` | Raw diagnostics only |
| Passive capture | — | Bounded recording, zero transmitted bytes |

Frames are six bytes with an additive checksum. The client address is `0x2E` and
the mainboard address is `0x11`. Only mainboard value frames count as device
readings; bridge echoes and remote requests do not confirm a setting.

Fan writes go to `0x11`, then remote multicast `0x20`. Temperature-step writes
go to `0x11`, `0x10`, then `0x20`. All transmitted packets pass an exact register,
recipient and value whitelist. Startup sends queries only. Reads and controls
wait for a quiet bus; control commands are not automatically replayed.

Heater enable/activity, bypass, device fault codes, firmware service timers,
CO₂/RH sensors and protection/calibration registers have not been verified for
this controller. No working controls or sensors are claimed for them.

## Home Assistant calculations

Filter dates, reminders, airflow estimates, fan-power estimates and building
ventilation figures belong to the Home Assistant layer. They are not additional
registers or meter readings. The library reports the underlying device values.

Supply-air warming can include electric post-heating. A temperature ratio alone
does not measure seasonal heat-recovery efficiency or heater electricity use.

## References

- [Digit S manual](https://pictures.suodatinkeskus.com/Vallox%20Digit%20S.pdf)
- [Digit SE manual, 1999](manuals/D_se_kho.pdf)
- [pvainio/vallox-rs485](https://github.com/pvainio/vallox-rs485)
- [Tom-Bom-badil/home-assistant_helios-vallox](https://github.com/Tom-Bom-badil/home-assistant_helios-vallox)

The SE manual is background documentation, not verification of an S register.
