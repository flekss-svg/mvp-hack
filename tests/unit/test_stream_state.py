import pandas as pd
import pytest

from app.engine.stream_state import StreamState, load_schedule_index, run_day


pytestmark = pytest.mark.unit


def event(k: int, fact: float) -> dict:
    return {
        "trip_id": "t1",
        "route_id": "r1",
        "direction_id": "0",
        "k": k,
        "stop_id": f"s{k}",
        "plan": 480.0 + k * 5,
        "fact": fact,
    }


def test_schedule_index_and_feature_horizon() -> None:
    stop_times = pd.DataFrame(
        {
            "trip_id": ["t1"] * 5,
            "stop_id": [f"s{i}" for i in range(5)],
            "arr_min": [480, 485, 490, 495, 500],
        }
    )
    schedule = load_schedule_index(stop_times)
    state = StreamState(schedule, route_mode={"r1": "tram"})

    features, horizon = state.features(event(0, 482.0))

    assert horizon == 3
    assert features["delay_now"] == 2.0
    assert features["ahead_plan_min"] == 15
    assert features["is_tram"] == 1


def test_run_day_builds_training_target() -> None:
    rows = [event(i, 480.0 + i * 5 + (4 if i >= 3 else 0)) for i in range(5)]
    frame = pd.DataFrame(rows)
    schedule = {"t1": ([f"s{i}" for i in range(5)], [480, 485, 490, 495, 500])}

    features, meta = run_day(StreamState(schedule), frame)

    assert len(features) == 2
    assert meta.iloc[0]["h"] == 3
    assert meta.iloc[0]["delay_future"] == 4
    assert meta.iloc[0]["y"] == 1
