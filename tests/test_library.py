"""Exercise the public library API, including actual socket transport."""

import asyncio
import importlib
import json
import shutil
import subprocess
import sys
from dataclasses import FrozenInstanceError

import pytest
from conftest import PKG, ROOT, Clock, Port, reader_module
from test_tcp_transport import unit

api = importlib.import_module(f"{PKG}.vallox_digit_s")
client_module = importlib.import_module(f"{PKG}.vallox_digit_s.client")


@pytest.fixture
def offline_client(monkeypatch, replies):
    clock = Clock()
    replies[0xA4] = 15
    port = Port(clock, replies)

    def factory(connection, **kwargs):
        return reader_module.ActiveReader(
            connection, lambda: port, clock=clock, wall_clock=clock.wall, **kwargs
        )

    monkeypatch.setattr(client_module, "ActiveReader", factory)
    with api.Client("socket://user:SECRET@private:1234") as client:
        yield client, port, clock


def test_read_only_includes_optional_temperature_request(offline_client):
    client, port, _ = offline_client
    assert client.status.state == api.ConnectionState.UNAVAILABLE
    status = client.read()
    assert status.state == api.ConnectionState.READY
    assert status.supply_temperature == 19
    assert status.fan_speed == 5 and status.temperature_step == 4
    assert len(port.sent) == 8 and all(packet[3] == 0 for packet in port.sent)
    assert port.closed
    assert len(status.samples) == 6
    assert json.loads(json.dumps(status.to_dict()))["state"] == "ready"
    with pytest.raises(FrozenInstanceError):
        status.fan_speed = 8
    with pytest.raises(api.ControlError, match="disabled"):
        client.set_fan_speed(6)
    assert len(port.sent) == 8


def test_status_expiry_and_detached_results(offline_client):
    client, port, clock = offline_client
    status = client.read()
    copy = status.to_dict()
    copy["fan_speed"] = 8
    assert client.status.fan_speed == 5
    count = len(port.sent)
    clock.advance(181)
    assert client.status.state == api.ConnectionState.UNAVAILABLE
    assert client.status.supply_temperature is None
    assert client.status.temperature_step is None
    assert len(port.sent) == count  # status never polls
    assert status.supply_temperature == 19  # old results are immutable snapshots


def test_transport_failure_is_reported_without_address(offline_client):
    client, port, _ = offline_client
    port.fail = "open"
    status = client.read()
    assert status.state == api.ConnectionState.UNAVAILABLE
    assert ("transport", "OSError") in status.errors
    assert "SECRET" not in json.dumps(status.to_dict()) + json.dumps(
        client.diagnostics()
    )
    assert port.closed


def test_closed_client_cannot_reopen(offline_client):
    client, _, _ = offline_client
    client.read()
    client.close()
    client.close()
    assert client.status.state == api.ConnectionState.CLOSED
    with pytest.raises(RuntimeError, match="closed"):
        client.read()
    with pytest.raises(RuntimeError, match="closed"):
        client.capture(1)


@pytest.mark.parametrize("seconds", [False, 0, -1, 301, 1.5, "1"])
def test_capture_duration_is_bounded(offline_client, seconds):
    client, port, _ = offline_client
    with pytest.raises(ValueError):
        client.capture(seconds)
    assert not port.opened and port.sent == []


def test_capture_is_passive(offline_client):
    client, port, _ = offline_client
    record = client.capture(1)
    assert record["received_bytes"] == 0
    assert record["frames"] == []
    assert port.sent == [] and port.closed


@pytest.mark.parametrize(
    "method,value",
    [
        ("set_fan_speed", 4),
        ("set_fan_speed", 9),
        ("set_fan_speed", True),
        ("set_fan_speed", 6.0),
        ("set_temperature_step", 0),
        ("set_temperature_step", 9),
        ("set_temperature_step", False),
    ],
)
def test_invalid_commands_never_open_transport(offline_client, method, value):
    client, port, _ = offline_client
    with pytest.raises(ValueError):
        getattr(client, method)(value)
    assert not port.opened and port.sent == []


@pytest.mark.parametrize("connection", [None, "", "   ", 1])
def test_connection_required(connection):
    with pytest.raises(ValueError):
        api.Client(connection)


def test_control_opt_in_is_boolean():
    with pytest.raises(TypeError):
        api.Client("/dev/ttyUSB0", allow_control="false")


def test_public_client_real_fan_command():
    pytest.importorskip("serialx")
    with unit() as (url, packets), api.Client(url, allow_control=True) as client:
        assert client.read().fan_speed == 6
        assert client.set_fan_speed(7).fan_speed == 7
        writes = [p for p in packets if not p.is_query]
        assert [(p.register, p.recipient, p.raw) for p in writes] == [
            (0x29, 0x11, 127),
            (0x29, 0x20, 127),
        ]
        with pytest.raises(api.ControlError):
            client.set_temperature_step(5)  # shared cooldown; no temperature write
        assert len([p for p in packets if not p.is_query]) == 2


def test_public_client_real_temperature_command():
    pytest.importorskip("serialx")
    with unit() as (url, packets), api.Client(url, allow_control=True) as client:
        assert client.read().temperature_step == 4
        assert client.set_temperature_step(5).temperature_step == 5
        writes = [p for p in packets if not p.is_query]
        assert [(p.register, p.recipient, p.raw) for p in writes] == [
            (0xA4, 0x11, 31),
            (0xA4, 0x10, 31),
            (0xA4, 0x20, 31),
        ]


def test_async_reads_are_serialized():
    pytest.importorskip("serialx")

    async def run(url):
        async with api.AsyncClient(url) as client:
            results = await asyncio.gather(client.read(), client.read())
            assert all(item.state == api.ConnectionState.READY for item in results)
            assert client.status.temperature_step == 4
        assert client.status.state == api.ConnectionState.CLOSED

    with unit() as (url, packets):
        asyncio.run(run(url))
        assert len(packets) == 16 and all(p.is_query for p in packets)


def test_async_cancel_closes_active_socket():
    pytest.importorskip("serialx")

    async def run(url):
        client = api.AsyncClient(url)
        task = asyncio.create_task(client.capture(30))
        try:
            for _ in range(200):
                if client.status.state == api.ConnectionState.LISTENING:
                    break
                await asyncio.sleep(0.005)
            assert client.status.state == api.ConnectionState.LISTENING
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
            assert client.status.state == api.ConnectionState.CLOSED
            with pytest.raises(RuntimeError, match="closed"):
                await client.read()
        finally:
            await client.aclose()

    with unit() as (url, packets):
        asyncio.run(run(url))
        assert packets == []


def test_async_close_interrupts_capture():
    pytest.importorskip("serialx")

    async def run(url):
        client = api.AsyncClient(url)
        task = asyncio.create_task(client.capture(30))
        try:
            for _ in range(200):
                if client.status.state == api.ConnectionState.LISTENING:
                    break
                await asyncio.sleep(0.005)
            assert client.status.state == api.ConnectionState.LISTENING
            await asyncio.wait_for(client.aclose(), 3)
            await asyncio.wait_for(task, 3)
            assert client.status.state == api.ConnectionState.CLOSED
        finally:
            await client.aclose()

    with unit() as (url, packets):
        asyncio.run(run(url))
        assert packets == []


def test_cancelling_queued_work_preserves_active_capture():
    pytest.importorskip("serialx")

    async def run(url):
        async with api.AsyncClient(url) as client:
            capture = asyncio.create_task(client.capture(30))
            for _ in range(200):
                if client.status.state == api.ConnectionState.LISTENING:
                    break
                await asyncio.sleep(.005)
            assert client.status.state == api.ConnectionState.LISTENING
            queued = asyncio.create_task(client.read())
            await asyncio.sleep(.01)
            queued.cancel()
            with pytest.raises(asyncio.CancelledError):
                await queued
            assert client.status.state == api.ConnectionState.LISTENING
            client.cancel_capture()
            await asyncio.wait_for(capture, 3)
            assert (await client.read()).state == api.ConnectionState.READY

    with unit() as (url, packets):
        asyncio.run(run(url))
        assert len(packets) == 8 and all(p.is_query for p in packets)


def test_import_without_home_assistant_in_fresh_process(tmp_path):
    # Like the wheel, expose only the standalone package. Adding the HA root
    # to sys.path would shadow Python's select module with HA's select.py.
    shutil.copytree(
        ROOT / "custom_components" / PKG / "vallox_digit_s",
        tmp_path / "vallox_digit_s",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from vallox_digit_s import Client, AsyncClient; "
        "assert not any(x.startswith('homeassistant') for x in sys.modules); "
        "c=Client('socket://example.invalid:8899'); "
        "assert c.status.state == 'unavailable'; c.close()"
    )
    subprocess.run([sys.executable, "-I", "-c", script, str(tmp_path)], check=True)
