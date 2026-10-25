"""One serialized reader; 60 s wire polling and 5 s local status updates."""
from __future__ import annotations
import asyncio
from datetime import timedelta
import logging
import time
from datetime import date
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from .const import CAPTURE_SECONDS, POLL_INTERVAL, UI_REFRESH_INTERVAL
from .speed_control import SpeedControlError
from .features import derived_values, finite, minimum_speed

LOGGER = logging.getLogger(__name__)


class DigitSCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, reader):
        super().__init__(
            hass, LOGGER, name=f"Digit S {entry.entry_id}", config_entry=entry,
            update_interval=timedelta(seconds=UI_REFRESH_INTERVAL),
        )
        self.reader = reader
        self.entry = entry
        self._wire_lock = asyncio.Lock()
        self._next_poll = 0.0
        self._capture_task = None
        self._stopping = False

    @property
    def capture_pending(self):
        return self._capture_task is not None and not self._capture_task.done()

    def _snapshot(self):
        data = self.reader.snapshot()
        def state_value(entity_id):
            state = self.hass.states.get(entity_id)
            return state.state if state else None
        data.update(derived_values(data, self.entry.options, dt_util.now().date(), state_value))
        return data

    async def async_options_updated(self, _hass, _entry):
        """Local calculations only; editing house data must not poll or write the bus."""
        self.async_set_updated_data(self._snapshot())

    async def async_set_filter_date(self, value):
        if not isinstance(value, date) or value > dt_util.now().date():
            raise HomeAssistantError("Valitse toteutunut vaihtopäivä, enintään tämä päivä.")
        source = self.entry.options.get("filter_date_entity")
        if source:
            domain = source.split(".")[0]
            if domain not in ("input_text", "input_datetime"):
                raise HomeAssistantError("Huoltopäivän apurityyppi ei ole sallittu.")
            service = "set_value" if domain == "input_text" else "set_datetime"
            key = "value" if domain == "input_text" else "date"
            await self.hass.services.async_call(domain, service, {"entity_id": source, key: value.isoformat()}, blocking=True)
        else:
            self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, "filter_changed": value.isoformat()})
        self.async_set_updated_data(self._snapshot())

    async def async_set_filter_interval(self, value):
        days = finite(value)
        if days is None or not days.is_integer() or not 1 <= days <= 730:
            raise HomeAssistantError("Huoltoväli on kokonaisluku 1–730 päivää.")
        source = self.entry.options.get("filter_interval_entity")
        if source:
            if not source.startswith("input_number."):
                raise HomeAssistantError("Huoltovälin on käytettävä input_number-apuria.")
            await self.hass.services.async_call("input_number", "set_value", {"entity_id": source, "value": int(days)}, blocking=True)
        else:
            self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, "filter_interval_days": int(days)})
        self.async_set_updated_data(self._snapshot())

    async def _async_update_data(self):
        # Updating sample age must NOT increase RS485 polling frequency.
        if self._stopping or self.capture_pending or self._wire_lock.locked():
            return self._snapshot()
        if time.monotonic() >= self._next_poll:
            async with self._wire_lock:
                await self.hass.async_add_executor_job(self.reader.sample)
                self._next_poll = time.monotonic() + POLL_INTERVAL
        return self._snapshot()

    async def async_start_capture(self):
        if self._stopping or self.capture_pending:
            return
        self.reader.prepare_capture()
        # HA tracks this long-lived task separately from setup completion.
        self._capture_task = self.entry.async_create_background_task(
            self.hass, self._async_capture(), f"Digit S capture {self.entry.entry_id}",
            eager_start=False,
        )
        self.async_set_updated_data(self._snapshot())

    async def _async_capture(self):
        try:
            async with self._wire_lock:
                if not self._stopping:
                    await self.hass.async_add_executor_job(self.reader.capture, CAPTURE_SECONDS)
        finally:
            # Resume normal polling on the next UI tick. No automatic setting writes.
            self._next_poll = 0.0
            if not self._stopping:
                self.async_set_updated_data(self._snapshot())

    async def async_cancel_capture(self):
        self.reader.cancel_capture()
        self.async_set_updated_data(self._snapshot())

    async def async_set_fan_speed(self, level):
        # All front ends (including the legacy number and automations) share
        # the same configured floor. A different entity must not bypass it.
        if type(level) is not int or not minimum_speed(self.entry.options) <= level <= 8:
            raise SpeedControlError("Valitse puhallintaso asetetun vähimmäistason ja tason 8 väliltä.")
        if self._stopping or self.capture_pending or self._wire_lock.locked():
            raise SpeedControlError("Lukukierros tai väylätallennus on käynnissä. Yritä hetken kuluttua.")
        try:
            async with self._wire_lock:
                await self.hass.async_add_executor_job(self.reader.set_fan_speed, level)
        finally:
            self._next_poll = 0.0
            # Publish after releasing the lock: entity availability includes
            # this lock, so publishing inside it leaves sibling controls
            # incorrectly unavailable until the next UI refresh.
            self.async_set_updated_data(self._snapshot())

    async def async_set_heating_level(self, level):
        if self._stopping or self.capture_pending or self._wire_lock.locked():
            raise SpeedControlError("Lukukierros tai väylätallennus on käynnissä. Yritä hetken kuluttua.")
        try:
            async with self._wire_lock:
                await self.hass.async_add_executor_job(self.reader.set_heating_level, level)
        finally:
            self._next_poll = 0.0
            self.async_set_updated_data(self._snapshot())

    def signal_stop(self):
        self._stopping = True
        self.reader.stop()

    async def async_stop(self):
        self.signal_stop()
        if self._capture_task is not None:
            try:
                await asyncio.shield(self._capture_task)
            except asyncio.CancelledError:
                pass
        # Wait for an already running poll/capture to close its own connection.
        async with self._wire_lock:
            await self.hass.async_add_executor_job(self.reader.wait_closed)
