import pytest

from app.data_sources.ndtp_protocol import Fix
from app.service.live_view import UNMATCHED_REASON, live_snapshot

pytestmark = pytest.mark.unit


def fix(unit_id: int, lat: float = 55.75, lon: float = 37.6, speed: int = 30) -> Fix:
    return Fix(unit_id=unit_id, gps_time=1_780_000_000, received_at=1_780_000_001.5,
               lon=lon, lat=lat, location_valid=True, speed=speed, course=90)


def kpi(snapshot: dict) -> dict:
    return {k["key"]: k["value"] for k in snapshot["kpi"]}


def test_vehicles_without_a_model_are_still_shown_without_risk() -> None:
    snap = live_snapshot([fix(1166336, 55.7, 37.5, 42), fix(7)], risk=None)

    assert snap["tracked"] == 2
    assert kpi(snap) == {"onLine": "2", "high": "0", "late": "0", "unmatched": "2"}
    assert snap["alerts"] == []
    v = snap["vehicles"][0]
    assert (v["vehicleId"], v["lat"], v["lon"], v["speed"]) == (1166336, 55.7, 37.5, 42)
    assert v["risk"] is None and v["level"] is None and v["route"] is None
    assert v["updatedAt"] == 1_780_000_001_500


def test_unmatched_vehicle_card_explains_why_there_is_no_forecast() -> None:
    card = live_snapshot([fix(5)], risk=None)["trips"][5]
    assert card["found"] and card["onLine"]
    assert card["forecastReason"] == UNMATCHED_REASON
    assert card["risk"] is None
    # level=3 у карточки значит «рейс скоро завершится» — для контекстной машины это неправда
    assert "level" not in card


def test_forecasts_from_the_event_stream_are_merged_in() -> None:
    risk = {"kpi": [{"key": "high", "value": "3"}, {"key": "late", "value": "1"}],
            "alerts": [{"tripId": "t1", "risk": 80}]}
    snap = live_snapshot([], risk)
    assert kpi(snap)["high"] == "3" and kpi(snap)["late"] == "1"
    assert snap["alerts"] == risk["alerts"]
    assert snap["vehicles"] == [] and snap["trips"] == {}
