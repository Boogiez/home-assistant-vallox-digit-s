"""Digit S client with bounded manual speed control and passive capture.

Each normal poll opens and closes its own connection at 9600 baud / 8N1.
The optional capture holds ONE port open, sends ZERO bytes and suspends polling.
"""
from __future__ import annotations
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import logging
import threading
import time
from .const import STALE_AFTER, VERSION
from .protocol import (
    CORE_REGISTERS, RAW_REGISTERS, REGISTERS, MAINBOARD, SENDER,
    FrameParser, convert, read_request, validate_read_request,
)
from .heating_control import heating_packet, validate_heating_packet, validate_heating_level, HEATING_RECIPIENTS
from .legacy_protocol import FAN_SPEEDS
from .speed_control import (
    SpeedControlError, validate_speed, speed_packet, validate_speed_packet,
    REMOTE_MULTICAST, COOLDOWN_SECONDS,
)

LOGGER = logging.getLogger(__name__)
# Engineering margin, not a manufacturer-specified minimum. The protocol allows
# 10 ms for an ACK/reply; 7 ms of quiet could precede that reply. Older pvainio
# implementation also uses a 100 ms quiet interval. Network timing is approximate.
QUIET_SECONDS = 0.100
SLOT_TIMEOUT = 2.0
RESPONSE_TIMEOUT = 1.0
WRITE_TIMEOUT = 1.0
MAX_ATTEMPTS = 2
TRACE_LIMIT = 512
CAPTURE_LIMIT = 4096


def utc_string(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="milliseconds")


class ActiveReader:
    def __init__(self, connection, factory=None, *, clock=None, wall_clock=None, control_enabled=False, read_temperature_request=None):
        self.connection = connection
        self.factory = factory
        self._clock = clock or time.monotonic
        self._wall = wall_clock or time.time
        self._state_lock = threading.RLock()
        self._io_lock = threading.Lock()
        self._stop = threading.Event()
        self._capture_stop = threading.Event()
        self.values = {}
        self._raw_registers = {}
        self.requests = self.responses = self.timeouts = self.invalid_values = 0
        self.rx_bytes = self.rx_frames = self.checksum_errors = self.discarded_bytes = 0
        self.bus_busy = self.blocked_transmissions = 0
        self.last_success = self.last_success_time = None
        self.last_error = None
        self.last_cycle_errors = {}
        self.last_cycle_responses = 0
        self.last_poll_time = None
        self.fan_speed_changes = 0
        self.previous_fan_speed = self.last_fan_speed_change = None
        self._last_known_fan_speed = None
        self.latest_remote_fan = None
        self.remote_fan_frames = 0
        self._parser = FrameParser()
        self._trace = deque(maxlen=TRACE_LIMIT)
        self._rx_tail = bytearray()
        self.capture_status = "Ei tallennusta"
        self.capture_active = False
        self.capture_started = self.capture_finished = None
        self.capture_received_bytes = self.capture_received_frames = 0
        self.capture_dropped_frames = 0
        self._capture_trace = deque(maxlen=CAPTURE_LIMIT)
        self._capture_deadline = None
        self.control_enabled = control_enabled
        self.read_temperature_request = control_enabled if read_temperature_request is None else read_temperature_request
        self.heating_status = "Ei lämpötilakomentoja"
        self.heating_commands = 0
        self.heating_requested = None
        self.optional_read_errors = {}
        self.control_status = "Ei nopeuskomentoja"
        self.control_commands = 0
        self.control_requested = None
        self._last_control_attempt = None

    def _make_port(self):
        if self.factory is not None:
            return self.factory()
        import serialx
        return serialx.serial_for_url(
            self.connection, baudrate=9600, parity=serialx.PARITY_NONE,
            stopbits=serialx.STOPBITS_ONE, byte_size=serialx.EIGHTBITS,
            read_timeout=1.0, write_timeout=1.0, connect_timeout=1.0,
        )

    def stop(self):
        """Cooperative shutdown; never close a port from a competing thread."""
        self._stop.set()
        self._capture_stop.set()

    def wait_closed(self):
        """Used on unload after stop(): wait for the owning I/O worker to finish."""
        with self._io_lock:
            pass

    def prepare_capture(self):
        if self._stop.is_set():
            raise RuntimeError("Integration is stopping")
        self._capture_stop.clear()
        with self._state_lock:
            self.capture_status = "Odottaa käynnistymistä"

    def cancel_capture(self):
        self._capture_stop.set()

    def _reset_stream(self):
        # Never join a fragment from an old serial session with a new one.
        self._parser = FrameParser()

    def _record_frame(self, frame, direction):
        record = {
            "time_utc": utc_string(self._wall()),
            "direction": direction,
            "frame": frame.packet.hex(" ").upper(),
            "sender": f"0x{frame.sender:02X}",
            "recipient": f"0x{frame.recipient:02X}",
            "kind": "read_request" if frame.is_query else "value_frame",
            "register": f"0x{(frame.raw if frame.is_query else frame.register):02X}",
            "raw_value": None if frame.is_query else frame.raw,
        }
        with self._state_lock:
            self._trace.append(record)
            if self.capture_active:
                if len(self._capture_trace) == CAPTURE_LIMIT:
                    self.capture_dropped_frames += 1
                self._capture_trace.append(record)

    def _accept_measurement(self, frame):
        # A remote's requested speed is NOT evidence of the actual mainboard value.
        if frame.sender != MAINBOARD or not 0x20 <= frame.recipient <= 0x2F:
            return
        if frame.register not in REGISTERS:
            return
        now = self._clock()
        stamp = utc_string(self._wall())
        name = REGISTERS[frame.register]
        value = convert(frame.register, frame.raw)
        with self._state_lock:
            self.last_success, self.last_success_time = now, stamp
            self._raw_registers[f"0x{frame.register:02X}"] = {
                "raw_decimal": frame.raw, "raw_hex": f"0x{frame.raw:02X}",
                "received_at_utc": stamp,
                "sender": f"0x{frame.sender:02X}",
                "recipient": f"0x{frame.recipient:02X}",
                "interpretation": "unconfirmed_raw_only" if frame.register in RAW_REGISTERS else "legacy_verified",
            }
            if value is None:
                self.invalid_values += 1
                self.values.pop(name, None)
                return
            if name == "fan_speed":
                if self._last_known_fan_speed is not None and self._last_known_fan_speed != value:
                    self.previous_fan_speed = self._last_known_fan_speed
                    self.fan_speed_changes += 1
                    self.last_fan_speed_change = stamp
                self._last_known_fan_speed = value
            self.values[name] = (value, now, frame.raw, stamp)

    def _ingest(self, data):
        old_crc, old_discarded = self._parser.checksum_errors, self._parser.discarded_bytes
        frames = self._parser.feed(data)
        with self._state_lock:
            self.rx_bytes += len(data)
            self.rx_frames += len(frames)
            self.checksum_errors += self._parser.checksum_errors - old_crc
            self.discarded_bytes += self._parser.discarded_bytes - old_discarded
            self._rx_tail.extend(data)
            del self._rx_tail[:-128]
            if self.capture_active:
                self.capture_received_bytes += len(data)
                self.capture_received_frames += len(frames)
        for frame in frames:
            self._record_frame(frame, "rx")
            if (frame.register == 0x29 and 0x21 <= frame.sender <= 0x2F
                    and frame.recipient in (0x10, MAINBOARD, 0x20)):
                speed = FAN_SPEEDS.get(frame.raw)
                if speed is not None:
                    with self._state_lock:
                        self.remote_fan_frames += 1
                        self.latest_remote_fan = {
                            "speed": speed, "sender": f"0x{frame.sender:02X}",
                            "recipient": f"0x{frame.recipient:02X}",
                            "time_utc": utc_string(self._wall()),
                            "note": "Observed remote value frame; not proof that the mainboard applied it",
                        }
            if not frame.is_query:
                self._accept_measurement(frame)
        return frames

    def _receive(self, port, timeout):
        one = bytearray(1)
        n = port.readinto(one, timeout=max(0.001, timeout))
        if n:
            return self._ingest(bytes(one[:n])), True
        return [], False

    def _free_slot(self, port):
        deadline = self._clock() + SLOT_TIMEOUT
        quiet_since = self._clock()
        while self._clock() < deadline and not self._stop.is_set():
            quiet_left = QUIET_SECONDS - (self._clock() - quiet_since)
            if quiet_left <= 0:
                return True
            _, received = self._receive(port, min(quiet_left, deadline - self._clock()))
            if received:
                quiet_since = self._clock()
        return False

    def _read_response(self, port, register):
        deadline = self._clock() + RESPONSE_TIMEOUT
        while self._clock() < deadline and not self._stop.is_set():
            frames, _ = self._receive(port, min(0.1, deadline - self._clock()))
            for frame in frames:
                if (frame.sender == MAINBOARD and frame.recipient == SENDER
                        and frame.register == register):
                    return frame.raw
        return None

    def _send(self, port, packet, *, fan_level=None, heating_level=None):
        try:
            if fan_level is not None and heating_level is not None:
                raise SpeedControlError("Ristiriitainen ohjauskomento estettiin.")
            if heating_level is not None:
                if not self.control_enabled:
                    raise SpeedControlError("Lämpötilaohjaus ei ole käytössä.")
                validate_heating_packet(packet, heating_level)
            elif fan_level is None:
                validate_read_request(packet)
            else:
                if not self.control_enabled:
                    raise SpeedControlError("Nopeusohjaus ei ole käytössä.")
                validate_speed_packet(packet, fan_level)
        except (ValueError, SpeedControlError):
            with self._state_lock:
                self.blocked_transmissions += 1
            raise
        if self._stop.is_set() or self.capture_active:
            raise RuntimeError("Transmission is disabled")
        pending = memoryview(packet)
        deadline = self._clock() + WRITE_TIMEOUT
        while pending:
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError("Serial write timeout")
            sent = port.write(pending, timeout=remaining)
            if not isinstance(sent, int) or sent <= 0 or sent > len(pending):
                raise TimeoutError("Invalid serial write result")
            pending = pending[sent:]
        # Record only a fully submitted request; partial sends produce an error.
        from .protocol import decode_frame
        self._record_frame(decode_frame(packet), "tx")

    def set_fan_speed(self, level):
        """One manual command pair, fresh readback, no automatic write retries.

        All polling, capture and controls share the same connection lock.
        Only 0x29 can be written, and only values for levels 1–8. No start/stop,
        minimum-speed register, protections, heater or persistent overrides.
        """
        validate_speed(level)
        if not self.control_enabled:
            raise SpeedControlError("Nopeusohjaus ei ole käytössä.")
        if self._stop.is_set() or self.capture_active:
            raise SpeedControlError("Ohjaus ei ole käytettävissä juuri nyt.")
        if not self._io_lock.acquire(blocking=False):
            raise SpeedControlError("Väylä on varattu. Yritä hetken kuluttua.")
        port = None
        try:
            now = self._clock()
            if self._last_control_attempt is not None and now - self._last_control_attempt < COOLDOWN_SECONDS:
                raise SpeedControlError("Odota kolme sekuntia ennen seuraavaa nopeuskomentoa.")
            if self.snapshot().get("fan_speed") is None:
                raise SpeedControlError("Tuore puhallintason mittaus puuttuu.")
            self._last_control_attempt = now
            self._reset_stream()
            port = self._make_port()
            port.open()

            def read_speed():
                if not self._free_slot(port):
                    raise SpeedControlError("Väylä on varattu; nopeutta ei varmistettu.")
                self._send(port, read_request(0x29))
                with self._state_lock:
                    self.requests += 1
                raw = self._read_response(port, 0x29)
                with self._state_lock:
                    if raw is None:
                        self.timeouts += 1
                    else:
                        self.responses += 1
                return convert(0x29, raw) if raw is not None else None

            # Never act on a stale value or a value merely echoed by the bridge.
            current = read_speed()
            if current is None:
                raise SpeedControlError("Kone ei vastannut; nopeuskomentoa ei lähetetty.")
            if current == level:
                with self._state_lock:
                    self.control_status = f"Taso {level} on jo käytössä"
                return self.snapshot()
            with self._state_lock:
                self.control_requested = level
                self.control_status = f"Varmistetaan tasoa {level}"
            # Same update sequence as the old LED-generation reference driver:
            # mainboard first, then synchronize the physical remotes.
            for recipient in (MAINBOARD, REMOTE_MULTICAST):
                if not self._free_slot(port):
                    raise SpeedControlError("Väylä varattu; komento jäi varmistamatta. Tarkista koneen taso.")
                self._send(port, speed_packet(level, recipient), fan_level=level)
                with self._state_lock:
                    self.control_commands += 1
            actual = None
            for _ in range(3):
                actual = read_speed()
                if actual == level:
                    with self._state_lock:
                        self.control_status = f"Koneelta vahvistettu taso {level}"
                    return self.snapshot()
            if actual is None:
                raise SpeedControlError("Komento lähetettiin, mutta koneen vastaus puuttuu. Tarkista puhallintaso.")
            raise SpeedControlError(f"Pyydetty taso {level}; kone ilmoittaa tason {actual}. Automaattisia uusintakomentoja ei lähetetty.")
        except Exception as exc:
            safe = str(exc) if isinstance(exc, SpeedControlError) else f"Yhteysvirhe nopeusohjauksessa ({type(exc).__name__}). Tarkista koneen taso."
            with self._state_lock:
                self.control_status = safe
            raise SpeedControlError(safe) from None
        finally:
            if port is not None:
                try:
                    port.close()
                except Exception:
                    LOGGER.warning("Digit S control connection close failed")
            self._io_lock.release()

    def set_heating_level(self, level):
        """One manual command pair, fresh readback, no automatic write retries.

        All polling, capture and controls share the same connection lock.
        Only A4 target-step masks 1–8 can be written. No heater-enable,
        duty-cycle, protection settings or persistent overrides.
        """
        validate_heating_level(level)
        if not self.control_enabled:
            raise SpeedControlError("Lämpötilaohjaus ei ole käytössä.")
        if self._stop.is_set() or self.capture_active:
            raise SpeedControlError("Ohjaus ei ole käytettävissä juuri nyt.")
        if not self._io_lock.acquire(blocking=False):
            raise SpeedControlError("Väylä on varattu. Yritä hetken kuluttua.")
        port = None
        try:
            now = self._clock()
            if self._last_control_attempt is not None and now - self._last_control_attempt < COOLDOWN_SECONDS:
                raise SpeedControlError("Odota kolme sekuntia ennen seuraavaa lämpötilakomentoa.")
            if self.snapshot().get("heating_level") is None:
                raise SpeedControlError("Tuore lämpötilaportaan mittaus puuttuu.")
            self._last_control_attempt = now
            self._reset_stream()
            port = self._make_port()
            port.open()

            def read_heating():
                if not self._free_slot(port):
                    raise SpeedControlError("Väylä on varattu; lämpötilaporrasta ei varmistettu.")
                self._send(port, read_request(0xA4))
                with self._state_lock:
                    self.requests += 1
                raw = self._read_response(port, 0xA4)
                with self._state_lock:
                    if raw is None:
                        self.timeouts += 1
                    else:
                        self.responses += 1
                return convert(0xA4, raw) if raw is not None else None

            # Never act on a stale value or a value merely echoed by the bridge.
            current = read_heating()
            if current is None:
                raise SpeedControlError("Kone ei vastannut; lämpötilakomentoa ei lähetetty.")
            if current == level:
                with self._state_lock:
                    self.heating_status = f"Lämpötilaporras {level} on jo käytössä"
                return self.snapshot()
            with self._state_lock:
                self.heating_requested = level
                self.heating_status = f"Varmistetaan lämpötilaporrasta {level}"
            # Same update sequence as the old LED-generation reference driver:
            # mainboard first, then synchronize the physical remotes.
            for recipient in HEATING_RECIPIENTS:
                if not self._free_slot(port):
                    raise SpeedControlError("Väylä varattu; komento jäi varmistamatta. Tarkista koneen taso.")
                self._send(port, heating_packet(level, recipient), heating_level=level)
                with self._state_lock:
                    self.heating_commands += 1
            actual = None
            for _ in range(3):
                actual = read_heating()
                if actual == level:
                    with self._state_lock:
                        self.heating_status = f"Koneelta vahvistettu lämpötilaporras {level}"
                    return self.snapshot()
            if actual is None:
                raise SpeedControlError("Komento lähetettiin, mutta koneen vastaus puuttuu. Tarkista lämpötilaporras.")
            raise SpeedControlError(f"Pyydetty lämpötilaporras {level}; kone ilmoittaa portaan {actual}. Automaattisia uusintakomentoja ei lähetetty.")
        except Exception as exc:
            safe = str(exc) if isinstance(exc, SpeedControlError) else f"Yhteysvirhe lämpötilaohjauksessa ({type(exc).__name__}). Tarkista koneen taso."
            with self._state_lock:
                self.heating_status = safe
            raise SpeedControlError(safe) from None
        finally:
            if port is not None:
                try:
                    port.close()
                except Exception:
                    LOGGER.warning("Digit S control connection close failed")
            self._io_lock.release()

    def sample(self):
        if self._stop.is_set() or not self._io_lock.acquire(blocking=False):
            return self.snapshot()
        port = None
        errors = {}
        self.optional_read_errors = {}
        answered = 0
        with self._state_lock:
            self.last_poll_time = utc_string(self._wall())
        try:
            self._reset_stream()
            port = self._make_port()
            port.open()
            for register in REGISTERS:
                if register == 0xA4 and not self.read_temperature_request:
                    continue
                if self._stop.is_set():
                    break
                result = "no_response"
                for _ in range(MAX_ATTEMPTS):
                    if self._stop.is_set():
                        break
                    if not self._free_slot(port):
                        with self._state_lock:
                            self.bus_busy += 1
                        result = "bus_busy"
                        continue
                    self._send(port, read_request(register))
                    with self._state_lock:
                        self.requests += 1
                    raw = self._read_response(port, register)
                    if raw is None:
                        with self._state_lock:
                            self.timeouts += 1
                        result = "no_response"
                        continue
                    with self._state_lock:
                        self.responses += 1
                    answered += 1
                    result = "ok" if convert(register, raw) is not None else "invalid_value"
                    break
                if result != "ok":
                    if register != 0xA4:
                        errors[f"0x{register:02X}"] = result
                    self.optional_read_errors[f"0x{register:02X}"] = result
        except Exception as exc:
            # No full exception strings: transports may embed credential-bearing URLs.
            errors["transport"] = type(exc).__name__
            LOGGER.warning("Digit S read failed (%s); details available in diagnostics", type(exc).__name__)
        finally:
            if port is not None:
                try:
                    port.close()
                except Exception:
                    errors["close"] = "close_failed"
            with self._state_lock:
                self.last_cycle_errors = errors
                self.last_cycle_responses = answered
                self.last_error = "; ".join(f"{key}: {value}" for key, value in errors.items()) or None
            self._io_lock.release()
        return self.snapshot()

    def capture(self, seconds=120):
        """Listen only. Not even a register query or protocol ACK is emitted."""
        if not 1 <= seconds <= 300:
            raise ValueError("Capture duration must be between 1 and 300 seconds")
        with self._io_lock:
            port = None
            error = None
            with self._state_lock:
                self.capture_active = True
                self.capture_status = "Tallennus käynnissä (vain kuuntelu)"
                self.capture_started = utc_string(self._wall())
                self.capture_finished = None
                self.capture_received_bytes = self.capture_received_frames = 0
                self.capture_dropped_frames = 0
                self._capture_trace.clear()
                self._capture_deadline = self._clock() + seconds
            try:
                if not self._stop.is_set() and not self._capture_stop.is_set():
                    self._reset_stream()
                    port = self._make_port()
                    port.open()
                    while (self._clock() < self._capture_deadline and not self._stop.is_set()
                           and not self._capture_stop.is_set()):
                        self._receive(port, min(0.1, self._capture_deadline - self._clock()))
            except Exception as exc:
                error = type(exc).__name__
                LOGGER.warning("Digit S passive capture failed (%s)", error)
            finally:
                if port is not None:
                    try:
                        port.close()
                    except Exception:
                        error = error or "close_failed"
                with self._state_lock:
                    self.capture_active = False
                    self.capture_finished = utc_string(self._wall())
                    self._capture_deadline = None
                    if error:
                        self.capture_status = f"Tallennus epäonnistui: {error}"
                    elif self._stop.is_set() or self._capture_stop.is_set():
                        self.capture_status = "Tallennus keskeytetty"
                    else:
                        self.capture_status = "Tallennus valmis"
        return self.snapshot()

    def snapshot(self):
        """No I/O. HA calls this every 5 s so sample ages really advance."""
        now = self._clock()
        with self._state_lock:
            result = {
                "read_requests": self.requests, "read_responses": self.responses,
                "read_timeouts": self.timeouts, "invalid_values": self.invalid_values,
                "received_bytes": self.rx_bytes, "received_frames": self.rx_frames,
                "checksum_errors": self.checksum_errors, "discarded_bytes": self.discarded_bytes,
                "bus_busy": self.bus_busy, "blocked_transmissions": self.blocked_transmissions,
                "last_error": self.last_error or "Ei virheitä",
                "last_success_time": self.last_success_time,
                "last_success_age": round(max(0, now - self.last_success)) if self.last_success is not None else None,
                "last_cycle_responses": self.last_cycle_responses,
                "fan_speed_changes": self.fan_speed_changes,
                "previous_fan_speed": self.previous_fan_speed,
                "fan_speed_last_change": self.last_fan_speed_change,
                "remote_fan_frames": self.remote_fan_frames,
                "last_remote_fan_speed": self.latest_remote_fan["speed"] if self.latest_remote_fan else None,
                "last_remote_fan_sender": self.latest_remote_fan["sender"] if self.latest_remote_fan else None,
                "capture_status": self.capture_status,
                "capture_active": self.capture_active,
                "capture_remaining": max(0, round(self._capture_deadline - now)) if self._capture_deadline else 0,
                "capture_frames": self.capture_received_frames,
                "heating_status": self.heating_status,
                "heating_commands": self.heating_commands,
                "heating_requested": self.heating_requested,
                "control_status": self.control_status,
                "control_commands": self.control_commands,
                "control_requested": self.control_requested,
                "_sample_times": {},
            }
            for key, (value, ts, raw, stamp) in self.values.items():
                if now - ts <= STALE_AFTER:
                    result[key] = value
                    result["raw_" + key] = raw
                    result["_sample_times"][key] = {"age_seconds": round(max(0, now - ts), 1), "received_at_utc": stamp}
            core_count = sum(name in result for name in CORE_REGISTERS.values())
            if self.capture_active:
                state = "Vain kuuntelu; lukukyselyt tauolla"
            elif core_count == 0:
                state = "Ei tuoreita mittauksia"
            elif core_count < len(CORE_REGISTERS) or self.last_cycle_errors:
                state = "Osittaiset lukutiedot"
            else:
                state = "Yhteys toimii"
            result["connection_state"] = state
            result["fresh_core_values"] = core_count

            def coherent(*keys):
                if not all(k in result for k in keys):
                    return False
                times = [self.values[k][1] for k in keys]
                return max(times) - min(times) <= 10.0

            out, sup, ext, exh = ("temperature_outdoor_air", "temperature_supply_air",
                                  "temperature_extract_air", "temperature_exhaust_air")
            if coherent(sup, out):
                result["supply_temperature_gain"] = result[sup] - result[out]
            if coherent(ext, exh):
                result["exhaust_temperature_drop"] = result[ext] - result[exh]
            if coherent(out, sup, ext) and result[ext] - result[out] >= 3:
                result["temperature_recovery_efficiency"] = round(
                    100 * (result[sup] - result[out]) / (result[ext] - result[out]), 1)
            return result

    def diagnostics(self):
        """JSON-compatible snapshot. Deliberately excludes connection and entry data."""
        with self._state_lock:
            return deepcopy({
                "integration_version": VERSION,
                "profile": "legacy_digit_s_verified_measurements_raw_settings",
                "transport_type": self.connection.split("://", 1)[0] if "://" in self.connection else "local_serial",
                "settings_writes_supported": self.control_enabled,
                "allowed_setting_writes": "manual 0x29 fan 1–8 and 0xA4 temperature step 1–8; no automatic replay",
                "transmit_policy": "fixed read requests plus validated manual fan/temperature packets; zero TX during capture",
                "poll_registers": [f"0x{r:02X}" for r in REGISTERS],
                "unconfirmed_registers": ["0xA9", "0xA5"],
                "quiet_seconds": QUIET_SECONDS,
                "snapshot": self.snapshot(),
                "last_poll_utc": self.last_poll_time,
                "last_poll_errors": dict(self.last_cycle_errors),
                "optional_poll_errors": dict(self.optional_read_errors),
                "latest_raw_registers": self._raw_registers,
                "latest_remote_fan_frame": self.latest_remote_fan,
                "recent_frames": list(self._trace),
                "recent_rx_bytes_hex": bytes(self._rx_tail).hex(" ").upper(),
                "passive_capture": {
                    "status": self.capture_status, "started_utc": self.capture_started,
                    "finished_utc": self.capture_finished,
                    "received_bytes": self.capture_received_bytes,
                    "received_frames": self.capture_received_frames,
                    "dropped_frames": self.capture_dropped_frames,
                    "frames": list(self._capture_trace),
                    "limitations": "Only traffic forwarded by the bridge is visible. A frame sequence alone does not establish causality.",
                },
            })
