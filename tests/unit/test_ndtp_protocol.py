import pytest

from app.data_sources.ndtp_protocol import FrameParser, crc16_modbus, fix_from_frame
from tests.factories import crc16_reference, ndtp_handshake, ndtp_realtime

pytestmark = pytest.mark.unit


def test_crc_matches_standard_check_value_and_bitwise_reference() -> None:
    assert crc16_modbus(b"123456789") == 0x4B37
    data = bytes(range(256)) * 3
    assert crc16_modbus(data) == crc16_reference(data)


def test_handshake_frame_fields() -> None:
    (frame,) = FrameParser().feed(ndtp_handshake(1166336))
    assert (frame.peer_address, frame.service_id, frame.nph_type) == (1166336, 0, 100)
    assert len(frame.body) == 18


@pytest.mark.parametrize("chunk", [1, 7, 10_000])
def test_stream_split_into_any_chunks(chunk: int) -> None:
    stream = ndtp_handshake(7) + ndtp_realtime(7) + ndtp_realtime(8)
    parser, frames = FrameParser(), []
    for i in range(0, len(stream), chunk):
        frames += parser.feed(stream[i:i + chunk])
    assert [(f.peer_address, f.nph_type) for f in frames] == [(7, 100), (7, 101), (8, 101)]


def test_garbage_and_false_signatures_are_skipped() -> None:
    parser = FrameParser()
    frames = parser.feed(b"\x00\x11\x7e" + ndtp_realtime(1) + b"\xff\xff\x7e\x7e\x01" + ndtp_realtime(2))
    assert [f.peer_address for f in frames] == [1, 2]
    assert parser.crc_errors == 0


def test_bad_crc_is_dropped_without_losing_the_next_frame() -> None:
    parser = FrameParser()
    frames = parser.feed(ndtp_realtime(1, crc_delta=1) + ndtp_realtime(2))
    assert [f.peer_address for f in frames] == [2]
    assert parser.crc_errors == 1
    wire, computed = parser.last_crc_mismatch
    assert wire != computed


def test_crc_check_can_be_disabled() -> None:
    assert len(FrameParser(verify_crc=False).feed(ndtp_realtime(1, crc_delta=1))) == 1


def fix(**kw):
    (frame,) = FrameParser().feed(ndtp_realtime(5, **kw))
    return fix_from_frame(frame, received_at=123.0)


def test_navigation_example_from_spec() -> None:
    f = fix()
    assert f.lat == pytest.approx(55.7551234, abs=1e-7)
    assert f.lon == pytest.approx(37.617321, abs=1e-7)
    assert f.location_valid
    assert (f.unit_id, f.gps_time, f.speed, f.course, f.received_at) == (5, 1_780_000_000, 40, 90, 123.0)


def test_southern_and_western_hemispheres() -> None:
    f = fix(lat=33.9, lon=18.4, north=False, east=False)
    assert (f.lat, f.lon) == (pytest.approx(-33.9, abs=1e-6), pytest.approx(-18.4, abs=1e-6))


@pytest.mark.parametrize("kw", [{"valid": False}, {"lat": 0.0, "lon": 0.0}])
def test_unusable_position_is_marked_invalid(kw: dict) -> None:
    assert not fix(**kw).location_valid


def test_handshake_is_not_a_position() -> None:
    (frame,) = FrameParser().feed(ndtp_handshake(5))
    assert fix_from_frame(frame, 0.0) is None
