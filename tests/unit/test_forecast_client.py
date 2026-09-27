import pytest

from app.service.forecast_client import ForecastClient

pytestmark = pytest.mark.unit


def test_live_snapshot_filters_stale_units_and_builds_alerts() -> None:
    client = ForecastClient("http://ml:8100")
    client._predictions[7] = {
        "predictionReady": True,
        "tripId": "trip-000007",
        "targetStopId": "stop-9",
        "currentDelaySec": 60,
        "risk": 0.82,
    }
    ndtp = {
        "units": [
            {"unitId": 7, "lastSeenSec": 1, "position": {"valid": True, "lon": 37.6, "lat": 55.7}},
            {"unitId": 8, "lastSeenSec": 121, "position": {"valid": True, "lon": 37.7, "lat": 55.8}},
        ]
    }
    snapshot = client.snapshot(ndtp)
    assert snapshot["tracked"] == 1
    assert snapshot["vehicles"]["id"] == [7]
    assert snapshot["vehicles"]["level"] == [2]
    assert snapshot["alerts"][0]["risk"] == 82
