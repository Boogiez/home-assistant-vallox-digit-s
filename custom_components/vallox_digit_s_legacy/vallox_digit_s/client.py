"""Blocking and asyncio interfaces over the shared RS485 reader."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Self, TypeVar

from .models import Status, status_from_snapshot
from .reader import ActiveReader
from .speed_control import SpeedControlError

T = TypeVar("T")


class ControlError(RuntimeError):
    """A command was refused or its result could not be confirmed.

    The device may already have applied a command. Read its state before retrying.
    """


class Client:
    """One client per physical bus. Construction does not open a connection.

    Reads query the controller; they do not change settings. Writes require
    allow_control=True, a recent reading and a successful mainboard readback.
    Each operation opens and closes its transport. close() is terminal.
    """

    def __init__(self, connection: str, *, allow_control: bool = False) -> None:
        if not isinstance(connection, str) or not connection.strip():
            raise ValueError("A serial connection or transparent TCP URL is required")
        if not isinstance(allow_control, bool):
            raise TypeError("allow_control must be a bool")
        self._reader = ActiveReader(
            connection, control_enabled=allow_control, read_temperature_request=True
        )
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Client is closed")

    @property
    def status(self) -> Status:
        """Cached state with current sample ages; no network traffic."""
        return status_from_snapshot(self._reader.snapshot(), closed=self._closed)

    def read(self) -> Status:
        """Poll all supported readings; inspect state/errors for partial replies."""
        self._ensure_open()
        return status_from_snapshot(self._reader.sample())

    def _control(self, method: Callable[[int], Any], value: int) -> Status:
        self._ensure_open()
        if not self._reader.control_enabled:
            raise ControlError(
                "Control is disabled; construct Client with allow_control=True"
            )
        try:
            return status_from_snapshot(method(value))
        except SpeedControlError:
            # Legacy status strings remain available in diagnostics for HA.
            # Do not expose transport URLs or an exception's private context.
            raise ControlError(
                "Command refused or not confirmed; read the unit before retrying"
            ) from None

    def set_fan_speed(self, level: int) -> Status:
        """Set a verified fan level (5–8), then return mainboard readback."""
        if type(level) is not int or not 5 <= level <= 8:
            raise ValueError("Fan level must be an integer from 5 to 8")
        return self._control(self._reader.set_fan_speed, level)

    def set_temperature_step(self, step: int) -> Status:
        """Set a temperature-request step (1–8), not a heater power setting."""
        if type(step) is not int or not 1 <= step <= 8:
            raise ValueError("Temperature step must be an integer from 1 to 8")
        return self._control(self._reader.set_heating_level, step)

    def capture(self, seconds: int = 120) -> dict[str, Any]:
        """Capture traffic for 1–300 seconds without transmitting any bytes.

        Returns the reader's JSON-compatible passive_capture diagnostic record.
        cancel_capture() may be called from another thread.
        """
        self._ensure_open()
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, int)
            or not 1 <= seconds <= 300
        ):
            raise ValueError(
                "Capture duration must be an integer from 1 to 300 seconds"
            )
        self._reader.prepare_capture()
        self._reader.capture(seconds)
        return self._reader.diagnostics()["passive_capture"]

    def cancel_capture(self) -> None:
        self._reader.cancel_capture()

    def diagnostics(self) -> dict[str, Any]:
        """Detached protocol diagnostics without the connection address."""
        return self._reader.diagnostics()

    def stop(self) -> None:
        """Request cooperative shutdown without waiting for a worker thread."""
        self._closed = True
        self._reader.stop()

    def close(self) -> None:
        """Stop current work and wait for its transport to close."""
        self.stop()
        self._reader.wait_closed()

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class AsyncClient:
    """Async adapter. Cancelling active I/O closes this client permanently.

    Operations run in a worker thread and are serialized. A cancelled worker is
    stopped cooperatively and awaited before cancellation reaches the caller.
    """

    def __init__(self, connection: str, *, allow_control: bool = False) -> None:
        self._client = Client(connection, allow_control=allow_control)
        self._lock = asyncio.Lock()

    @property
    def status(self) -> Status:
        return self._client.status

    async def _run(self, method: Callable[..., T], *args: Any) -> T:
        async with self._lock:
            task = asyncio.create_task(asyncio.to_thread(method, *args))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                self._client.stop()
                # Further cancellation must not orphan a worker holding the bus.
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                    except Exception:  # noqa: BLE001 - preserve cancellation over worker errors
                        break
                if not task.cancelled():
                    task.exception()  # Retrieve an error without replacing cancellation.
                raise

    async def read(self) -> Status:
        return await self._run(self._client.read)

    async def set_fan_speed(self, level: int) -> Status:
        return await self._run(self._client.set_fan_speed, level)

    async def set_temperature_step(self, step: int) -> Status:
        return await self._run(self._client.set_temperature_step, step)

    async def capture(self, seconds: int = 120) -> dict[str, Any]:
        return await self._run(self._client.capture, seconds)

    def cancel_capture(self) -> None:
        self._client.cancel_capture()

    def diagnostics(self) -> dict[str, Any]:
        return self._client.diagnostics()

    async def aclose(self) -> None:
        self._client.stop()  # Interrupt capture before waiting for the lock.
        await self._run(self._client.close)

    async def __aenter__(self) -> Self:
        self._client._ensure_open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
