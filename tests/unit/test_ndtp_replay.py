"""Пакеты проигрывателя треков должен разбирать боевой парсер приемника — иначе демо молча пустое."""
import importlib.util
from pathlib import Path

import pytest

from app.data_sources.ndtp_protocol import FrameParser, fix_from_frame

pytestmark = pytest.mark.unit

_path = Path(__file__).resolve().parents[2] / "scripts" / "ndtp_replay.py"
_spec = importlib.util.spec_from_file_location("ndtp_replay", _path)
replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay)


def parse(data: bytes):
    parser = FrameParser(True)
    return parser, parser.feed(data)


def test_realtime_packet_roundtrips_through_the_real_parser() -> None:
    data = replay.handshake(1166336) + replay.realtime(1166336, 1_767_700_000, 55.7551234, 37.617321, True, 33, 270)
    parser, frames = parse(data)
    assert parser.crc_errors == 0 and len(frames) == 2
    fix = fix_from_frame(frames[1], 0.0)
    assert (fix.unit_id, fix.gps_time, fix.location_valid, fix.speed, fix.course) == (1166336, 1_767_700_000, True, 33, 270)
    assert (fix.lat, fix.lon) == pytest.approx((55.7551234, 37.617321), abs=1e-6)


def test_missing_coordinates_are_sent_as_an_invalid_fix() -> None:
    _, frames = parse(replay.realtime(5, 1_767_700_000, float("nan"), float("nan"), True, 0, 0))
    assert fix_from_frame(frames[0], 0.0).location_valid is False
