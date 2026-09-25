import pandas as pd
import pytest

from app.data_sources.gps_telemetry import decode_ndtp, pings_to_events, synth_pings
from app.domain.schema import STOP_EVENT_COLUMNS


pytestmark = pytest.mark.unit


def test_synthetic_gps_round_trip_recovers_stop_events() -> None:
    stops = ["s0", "s1", "s2", "s3"]
    stops_xy = {stop: (37.60 + i * 0.005, 55.75) for i, stop in enumerate(stops)}
    schedule = {"t1": (stops, [480.0, 485.0, 490.0, 495.0])}
    events = pd.DataFrame([
        {
            "trip_id": "t1",
            "route_id": "r1",
            "direction_id": "0",
            "k": i,
            "stop_id": stop,
            "plan": 480.0 + i * 5,
            "fact": 481.0 + i * 5,
        }
        for i, stop in enumerate(stops)
    ])

    pings = synth_pings(events, stops_xy, every_sec=10, noise_m=0, seed=42)
    recovered = pings_to_events(pings, schedule, stops_xy)

    assert list(recovered.columns) == STOP_EVENT_COLUMNS
    assert recovered["stop_id"].tolist() == stops
    assert ((recovered["fact"] - events["fact"]).abs() * 60).max() <= 10


def test_too_few_known_stops_returns_empty_canonical_frame() -> None:
    pings = pd.DataFrame([{
        "trip_id": "t1",
        "route_id": "r1",
        "direction_id": "0",
        "ts_min": 480.0,
        "lat": 55.75,
        "lon": 37.60,
    }])
    result = pings_to_events(
        pings,
        {"t1": (["s0", "s1"], [480.0, 485.0])},
        {"s0": (37.60, 55.75), "s1": (37.61, 55.75)},
    )
    assert result.empty
    assert list(result.columns) == STOP_EVENT_COLUMNS


def test_ndtp_decoder_is_explicitly_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="спецификации NDTP"):
        decode_ndtp(b"payload")
