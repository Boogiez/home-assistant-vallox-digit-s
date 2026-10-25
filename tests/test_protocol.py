import pytest
from conftest import protocol as p, frame


def test_preserve_verified_map_and_complete_ntc():
    assert p.CORE_REGISTERS == {0x58:"temperature_outdoor_air", 0x5B:"temperature_supply_air",
        0x5A:"temperature_extract_air", 0x5C:"temperature_exhaust_air", 0x29:"fan_speed"}
    assert len(p.NTC5K) == 256
    assert p.NTC5K[0] == -74
    assert p.NTC5K[255] == 100


@pytest.mark.parametrize("speed", range(1, 9))
def test_all_current_fan_levels(speed):
    assert p.convert(0x29, (1 << speed) - 1) == speed


@pytest.mark.parametrize("register", [0xA9, 0xA5])
@pytest.mark.parametrize("raw", [0, 4, 15, 31, 63, 127, 255])
def test_unconfirmed_settings_remain_raw(register, raw):
    assert p.convert(register, raw) == raw


@pytest.mark.parametrize("raw", [0, 2, 4, 0x11, -1, 256, True, None, "31"])
def test_invalid_current_fan_never_falls_back_to_one(raw):
    assert p.convert(0x29, raw) is None


def test_temperature_limits_and_zero_sentinel():
    assert p.convert(0x58, 0) is None
    assert p.convert(0x58, 255) is None
    assert p.convert(0x32, 100) is None  # do not switch to the newer map
    assert p.convert(0x58, p.NTC5K.index(13)) == 13


def test_exact_read_whitelist_exhaustive():
    for register in range(256):
        if register in p.REGISTERS:
            packet = p.read_request(register)
            p.validate_read_request(packet)
            assert packet == frame(0x2E, 0x11, 0, register)
        else:
            with pytest.raises(ValueError): p.read_request(register)
            with pytest.raises(ValueError): p.validate_read_request(frame(0x2E, 0x11, 0, register))


@pytest.mark.parametrize("packet", [
    frame(0x2E,0x11,0x29,0x3F), frame(0x2E,0x20,0x29,0x7F),
    frame(0x2E,0x11,0xA9,0x1F), frame(0x2E,0x11,0x06,1),
    frame(0x2E,0x11,0x8F,0), frame(0x2E,0x11,0x91,0),
    frame(0x21,0x11,0,0x29), frame(0x2E,0x10,0,0x29),
    p.read_request(0x29) + b"\x69", b"\x69", b"", b"\x01\x2e\x11\x00\x29\x00",
])
def test_tx_rejects_writes_ack_wrong_addresses_and_malformed_frames(packet):
    with pytest.raises(ValueError): p.validate_read_request(packet)


def test_fragmented_frame_query_echo_noise_bad_checksum():
    parser = p.FrameParser()
    a, b = p.read_request(0x29), frame(0x11,0x2E,0x29,0x3F)
    bad = b[:-1] + bytes([b[-1] ^ 1])
    records = []
    for byte in b"\x88\x99" + bad + a + b:
        records.extend(parser.feed(bytes([byte])))
    assert len(records) == 2
    assert records[0].is_query
    assert not records[1].is_query and records[1].raw == 0x3F
    assert parser.checksum_errors >= 1 and parser.discarded_bytes >= 2
    assert len(parser.buffer) < 6


def test_unknown_register_retained_in_frame_parser():
    decoded = p.decode_frame(frame(0x21,0x11,0x77,0x44))
    assert decoded.register == 0x77 and decoded.raw == 0x44
    assert p.convert(decoded.register, decoded.raw) is None
