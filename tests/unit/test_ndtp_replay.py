import pytest

from app.data_sources.ndtp_protocol import FrameParser, fix_from_frame
from scripts.ndtp_replay import handshake, parse_clock, realtime

pytestmark = pytest.mark.unit


def test_player_frames_are_accepted_by_backend_protocol() -> None:
    parser = FrameParser()
    frames = parser.feed(
        handshake(123) + realtime(123, 1_780_000_000, 37.617321, 55.7551234, 32, True)
    )
    assert [(frame.peer_address, frame.nph_type) for frame in frames] == [(123, 100), (123, 101)]
    fix = fix_from_frame(frames[1], 0.0)
    assert fix is not None
    assert fix.speed == 32
    assert fix.location_valid


def test_player_clock_validation() -> None:
    assert parse_clock("06:00") == 21600
    with pytest.raises(ValueError):
        parse_clock("25:00")
