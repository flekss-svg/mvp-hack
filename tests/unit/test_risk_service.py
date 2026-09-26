from types import SimpleNamespace

import numpy as np
import pytest

from app.engine.feature_definitions import FEATURES
from app.service.risk_service import RiskService


pytestmark = pytest.mark.unit


class FakePredictor:
    def predict_risk(self, features):
        assert not features.empty
        return np.full(len(features), 0.8)

    def explain(self, features):
        contrib = np.zeros((len(features), len(FEATURES)))
        contrib[:, FEATURES.index("lead_headway_dev")] = 1.0
        return contrib


class FakeRegressor:
    def predict_delay(self, features):
        return np.full(len(features), 4.0)


def make_artifacts():
    stops = [f"s{i}" for i in range(5)]
    return SimpleNamespace(
        predictor=FakePredictor(),
        regressor=FakeRegressor(),
        hist_profile={},
        schedule={"t1": (stops, [480, 485, 490, 495, 500])},
        route_mode={"r1": "bus"},
        route_name={"r1": "42"},
        stop_name={stop: f"Stop {i}" for i, stop in enumerate(stops)},
    )


def event(k: int, fact: float, trip_id: str = "t1") -> dict:
    return {
        "trip_id": trip_id,
        "route_id": "r1",
        "direction_id": "0",
        "k": k,
        "stop_id": f"s{k}",
        "plan": 480.0 + k * 5,
        "fact": fact,
    }


def test_ingest_filter_snapshot_and_trip_completion() -> None:
    service = RiskService(make_artifacts())
    service.set_context(rain=0.5, holiday=1)

    assert service.schedule_size == 1
    assert service.ingest_events([event(0, 481.0), event(0, 481.0, "unknown")]) == 1
    assert service.current_risk(min_risk=0.9) == []
    assert service.current_risk(limit=1)[0]["risk"] == 0.8

    snapshot = service.snapshot()
    assert snapshot["tracked"] == 1
    assert snapshot["alerts"][0] == {
        "tripId": "t1",
        "route": "42",
        "mode": "bus",
        "dest": "Stop 4",
        "stop": "Stop 0",
        "delay": 1.0,
        "risk": 80,
        # прогноз на остановку ~12 мин вперед (s3, план 495) и почему
        "currentTime": "08:01",
        "forecastStop": "Stop 3",
        "scheduledArrival": "08:15",
        "forecastDelay": 4.0,
        "expectedArrival": "08:19",
        "forecastMinutes": 18,
        "forecastReason": "Сбился интервал с впереди идущей машиной",
    }

    assert service.ingest_events([event(4, 501.0)]) == 0
    assert service.current_risk() == []


def test_trip_that_ends_within_the_same_batch_is_not_left_in_alerts() -> None:
    service = RiskService(make_artifacts())
    # середина рейса и его конечная пришли одной пачкой
    assert service.ingest_events([event(0, 481.0), event(4, 501.0)]) == 1
    assert service.current_risk() == []
    assert service.snapshot()["alerts"] == []
