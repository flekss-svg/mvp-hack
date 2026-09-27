import pytest

from app.data_sources.ndtp_protocol import FrameParser, crc16_modbus, fix_from_frame
from tests.factories import crc16_reference, ndtp_handshake, ndtp_realtime

pytestmark = pytest.mark.unit


def test_crc_and_chunked_stream() -> None:
    assert crc16_modbus(b"123456789") == 0x4B37
    data = bytes(range(256))
    assert crc16_modbus(data) == crc16_reference(data)
    stream = ndtp_handshake(7) + ndtp_realtime(7)
    parser = FrameParser()
    frames = []
    for offset in range(0, len(stream), 3):
        frames.extend(parser.feed(stream[offset:offset + 3]))
    assert [(frame.peer_address, frame.nph_type) for frame in frames] == [(7, 100), (7, 101)]


def test_navigation_fix_and_bad_crc() -> None:
    parser = FrameParser()
    frames = parser.feed(ndtp_realtime(1, crc_delta=1) + ndtp_realtime(2))
    assert [frame.peer_address for frame in frames] == [2]
    assert parser.crc_errors == 1
    fix = fix_from_frame(frames[0], received_at=123.0)
    assert fix is not None
    assert fix.lat == pytest.approx(55.7551234)
    assert fix.lon == pytest.approx(37.617321)
    assert fix.received_at == 123.0


def test_invalid_navigation_position() -> None:
    (frame,) = FrameParser().feed(ndtp_realtime(5, valid=False))
    fix = fix_from_frame(frame, 0.0)
    assert fix is not None
    assert not fix.location_valid
