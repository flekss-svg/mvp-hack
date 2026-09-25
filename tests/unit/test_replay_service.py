import pytest

from app.service.replay_service import hhmm


pytestmark = pytest.mark.unit


def test_hhmm_wraps_service_day() -> None:
    assert hhmm(8 * 60 + 5) == "08:05"
    assert hhmm(24 * 60 + 15) == "00:15"


def test_day_frame_timeline_and_trip(replay_service) -> None:
    day = replay_service.day_info()
    assert day["trips"] == 1
    assert day["network"]["segments"] == [[0, 1]]

    frame = replay_service.frame(485.0, trip_id=0)
    assert frame["clock"] == "08:05"
    assert frame["vehicles"]["id"] == [0]
    assert frame["vehicles"]["risk"] == [80]
    assert frame["trip"]["found"] is True
    assert frame["alerts"][0]["route"] == "42"

    timeline = replay_service.timeline()
    assert timeline["tMin"] == 480.0
    assert timeline["bins"]


def test_unknown_trip_is_reported(replay_service) -> None:
    assert replay_service.trip(99, 485.0) == {"found": False}
