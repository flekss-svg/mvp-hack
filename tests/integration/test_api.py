import json

import pytest
from fastapi.testclient import TestClient

import app.api as api_module


pytestmark = pytest.mark.integration


@pytest.fixture
def client(monkeypatch, tmp_path, replay_service, live_service) -> TestClient:
    metrics = {
        "early_warning": [
            {"precision_at_recall70": 0.83, "pr_auc": 0.87},
            {"precision_at_recall70": 0.56, "pr_auc": 0.66},
        ],
        "n_test_early": 100,
        "feature_importance": {"delay_now": 10.0},
        "feature_descriptions": {"delay_now": "Текущее опоздание"},
    }
    (tmp_path / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    monkeypatch.setattr(api_module, "REPORTS", tmp_path)
    monkeypatch.setattr(api_module, "_replay", api_module.Lazy("replay", lambda: replay_service, "hint"))
    monkeypatch.setattr(api_module, "_live", api_module.Lazy("live", lambda: live_service, "hint"))
    return TestClient(api_module.app)


def test_health_and_model(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["sources"]["replay"]["ready"] is True

    model = client.get("/api/model")
    assert model.status_code == 200
    assert model.json()["precision"] == 83


def test_replay_endpoints_and_validation(client: TestClient) -> None:
    assert client.get("/api/replay/day").status_code == 200
    frame = client.get("/api/replay/frame", params={"t": 485, "mode": "bus"})
    assert frame.status_code == 200
    assert frame.json()["vehicles"]["id"] == [0]
    assert client.get("/api/replay/timeline").status_code == 200
    assert client.get("/api/replay/frame", params={"t": 485, "mode": "metro"}).status_code == 400
    assert client.get("/api/replay/frame").status_code == 422


def test_live_write_and_read_endpoints(client: TestClient, live_service) -> None:
    payload = [{
        "trip_id": "t1",
        "route_id": "r1",
        "direction_id": "0",
        "k": 0,
        "stop_id": "s0",
        "plan": 480,
        "fact": 481,
    }]
    assert client.post("/api/events", json=payload).json() == {"accepted": 1, "scored": 1}
    assert client.post("/api/events", json=[{"trip_id": "broken"}]).status_code == 422
    assert client.post("/api/context", json={"rain": 0.7, "holiday": 1}).json() == {"ok": True}
    assert live_service.context == {"rain": 0.7, "holiday": 1}
    assert client.get("/api/live/snapshot").status_code == 200
    assert client.get("/api/risk", params={"limit": 5, "min_risk": 0.5}).json()[0]["risk"] == 0.8


def test_ndtp_units_endpoint(client: TestClient) -> None:
    units = client.get("/api/live/units")
    assert units.status_code == 200
    assert {"listening", "port", "stats", "units"} <= units.json().keys()
    assert "ndtp" in client.get("/api/health").json()["sources"]
