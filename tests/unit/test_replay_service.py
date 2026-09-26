import pytest

from app.service.replay_service import hhmm
from tests.factories import LEAD_REASON


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


def test_alert_explains_the_forecast(replay_service) -> None:
    (alert,) = replay_service.frame(485.0)["alerts"]
    assert alert["forecastReason"] == LEAD_REASON
    assert alert["forecastStop"] == "Конечная"
    assert alert["scheduledArrival"] == "08:07"          # план 487 мин
    assert alert["forecastDelay"] == 4.0                 # регрессор: ждем +4 мин
    assert alert["expectedArrival"] == "08:11"
    assert alert["forecastMinutes"] == 6                 # 487 + 4 - 485
    # другая машина прошла перегон на 2 мин медленнее плана в 08:02 — это и есть участок
    assert alert["problemSegment"] == {"from": "Начальная", "to": "Конечная", "index": 0, "excess": 2.0}


def test_trip_card_carries_the_same_forecast(replay_service) -> None:
    card = replay_service.trip(0, 485.0)
    assert card["forecastReason"] == LEAD_REASON
    assert card["expectedArrival"] == "08:11"


def test_no_forecast_fields_where_the_model_gave_no_forecast(replay_service) -> None:
    card = replay_service.trip(0, 490.0)          # последняя остановка рейса: прогноза нет
    assert "forecastReason" not in card and "forecastDelay" not in card
