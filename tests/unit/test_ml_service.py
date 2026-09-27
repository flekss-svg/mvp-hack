from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml_service.server import ForecastEngine, TelemetryPing

pytestmark = pytest.mark.unit


class FakeModel:
    feature_names_ = [
        "cur_dev_s", "horizon_s", "tgt_min_of_day", "last_ping_age_s", "speed_last",
        "speed_mean_120", "stopped_share_120", "path_m_120", "eff_speed_120",
        "speed_mean_300", "stopped_share_300", "path_m_300", "eff_speed_300",
        "speed_mean_600", "stopped_share_600", "path_m_600", "eff_speed_600",
        "pos_age_s", "dist_straight_m", "n_stops_ahead", "dist_route_m", "req_speed",
        "phys_delay_300", "phys_delay_600",
    ]

    def predict(self, features):
        assert list(features.columns) == self.feature_names_
        return np.array([240.0])


def test_realtime_forecast_after_ten_minute_warmup(tmp_path: Path) -> None:
    engine = ForecastEngine(tmp_path, tmp_path / "missing.cbm")
    engine.model = FakeModel()
    engine.feature_names = list(FakeModel.feature_names_)
    base = 1_780_000_000
    plan = pd.DataFrame({
        "tt_action_item_id": ["s0", "s1", "s2"],
        "tr_id": ["trip-1"] * 3,
        "t_plan": [base, base + 600, base + 1350],
        "s_lat": [55.70, 55.71, 55.72],
        "s_lon": [37.50, 37.51, 37.52],
    })
    engine.plan = plan
    engine.plan_by_trip = {"trip-1": plan}
    first = engine.predict(TelemetryPing(
        unit_id=1, tr_id="trip-1", event_time=base, lat=55.70, lon=37.50, speed=20
    ))
    assert first["predictionReady"] is False
    result = engine.predict(TelemetryPing(
        unit_id=1, tr_id="trip-1", event_time=base + 600, lat=55.71, lon=37.51, speed=25
    ))
    assert result["predictionReady"] is True
    assert result["targetDelaySec"] == 240.0
    assert result["horizonSec"] == 750
