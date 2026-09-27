"""Live-срез с прогнозами по модели хакатона (ml_service/live.py) в формате, который рисует фронтенд."""
import json

import pytest

from app.data_sources.ndtp_protocol import Fix
from app.service.live_view import UNMATCHED_REASON, live_snapshot

pytestmark = pytest.mark.unit

T = 1_780_000_000


def fix(unit_id: int) -> Fix:
    return Fix(unit_id=unit_id, gps_time=T, received_at=T + 1.5, lon=37.6, lat=55.75,
               location_valid=True, speed=30, course=90)


def kpi(snapshot: dict) -> dict:
    return {k["key"]: k["value"] for k in snapshot["kpi"]}


def forecast(unit_id: int, p_late: float = 0.0, cur_dev_s: float | None = 60.0, status: str = "ok") -> dict:
    base = {"unit_id": unit_id, "tr_id": "tr1", "T": T, "speed": 30.0, "status": status, "last_ping": T}
    if status != "ok":
        return base
    return {**base, "target_stop_id": "s9", "target_stop": "Ленинский пр., д.1", "target_plan": T + 700,
            "delay_s": 150.0, "cur_dev_s": cur_dev_s, "cur_dev_source": "arrival", "p_early": 0.0,
            "p_ontime": 1 - p_late, "p_late": p_late, "reasons": ["долгий простой за последние 10 мин"]}


def test_no_forecasts_keeps_the_old_behaviour_and_the_event_stream_alerts() -> None:
    risk = {"kpi": [{"key": "high", "value": "3"}], "alerts": [{"tripId": "t1", "risk": 80}]}
    old = live_snapshot([fix(1)], risk)
    assert live_snapshot([fix(1)], risk, None) == old
    assert live_snapshot([fix(1)], risk, {}) == old       # прогнозист загружен, но потока еще нет
    assert old["alerts"] == risk["alerts"]


def test_matched_vehicles_get_risk_level_alert_and_card_from_the_model() -> None:
    snap = live_snapshot([fix(1), fix(2), fix(3), fix(4)], None, {
        1: {**forecast(1, 0.85, cur_dev_s=30.0),  # высокий риск, еще не опаздывает -> тревога
            "route": "м17", "route_name": "Метро «Щукинская» — Строгино", "mode": "bus"},
        2: forecast(2, 0.10),                     # низкий риск
        3: forecast(3, 0.92, cur_dev_s=400.0),    # высокий риск, но уже опаздывает -> без тревоги
    })                                            # 4 — нет расписания: контекстная машина
    assert kpi(snap) == {"onLine": "4", "high": "2", "late": "1", "unmatched": "1"}
    assert [a["tripId"] for a in snap["alerts"]] == [1]
    alert = snap["alerts"][0]
    assert alert["risk"] == 85 and alert["stop"] == "Ленинский пр., д.1" and alert["delay"] == 0.5

    by_id = {v["vehicleId"]: v for v in snap["vehicles"]}
    assert (by_id[1]["risk"], by_id[1]["level"]) == (85, 2)
    assert (by_id[2]["risk"], by_id[2]["level"]) == (10, 0)
    assert by_id[4]["risk"] is None and by_id[4]["level"] is None
    # Номер маршрута ML восстановил по остановкам расписания; не восстановил — tr_id за маршрут не выдаем.
    assert (by_id[1]["route"], by_id[1]["mode"]) == ("м17", "bus")
    assert by_id[2]["route"] is None and by_id[4]["route"] is None
    assert alert["route"] == "м17" and alert["mode"] == "bus"

    card = snap["trips"][1]
    assert card["route"] == "м17" and card["routeName"] == "Метро «Щукинская» — Строгино · tr_id tr1"
    assert card["level"] == 2 and card["forecastDelay"] == 2.5
    assert snap["trips"][2]["route"] == "—"
    assert snap["trips"][2]["routeName"] == "Номер маршрута не определен · tr_id tr1"
    assert card["scheduledArrival"] != card["expectedArrival"]
    assert card["forecastReason"] == "Долгий простой за последние 10 мин"
    assert snap["trips"][4]["forecastReason"] == UNMATCHED_REASON


def test_snapshot_never_contains_nan_because_the_api_cannot_serialize_it() -> None:
    nan = float("nan")
    fc = {**forecast(1, 0.9, cur_dev_s=nan), "speed": nan}
    snap = live_snapshot([fix(1)], None, {1: fc})
    json.dumps(snap, allow_nan=False)                       # как это делает FastAPI: NaN -> ValueError
    assert snap["vehicles"][0]["delay"] is None and snap["trips"][1]["averageSpeed"] is None


def test_matched_vehicle_without_a_forecast_says_why() -> None:
    snap = live_snapshot([fix(1)], None, {1: forecast(1, status="no_target")})
    assert snap["vehicles"][0]["level"] is None
    assert "нет остановки" in snap["trips"][1]["forecastReason"]
    assert kpi(snap)["high"] == "0" and snap["alerts"] == []


def test_card_without_forecast_uses_the_same_clock_as_forecasts() -> None:
    snap = live_snapshot([fix(1), fix(2)], None, {1: forecast(1, 0.1)})
    # время карточки не должно зависеть от часового пояса компьютера
    assert snap["trips"][2]["currentTime"] == snap["trips"][1]["currentTime"] == snap["clock"]
