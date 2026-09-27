"""ML-модуль отдельным сервисом: HTTP-контракт ml_service/server.py и клиент backend (app/service/ml_client.py)."""
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

import ml_service.server as server
from app.data_sources.ndtp_protocol import Fix
from app.service.ml_client import RemoteForecaster

pytestmark = pytest.mark.integration


class FakeForecaster:
    units = {7}

    def __init__(self) -> None:
        self.seen = []

    def ingest(self, fix) -> bool:
        self.seen.append((fix.unit_id, fix.gps_time, fix.location_valid))
        return fix.unit_id == 7

    def forecasts(self) -> dict:
        return {7: {"unit_id": 7, "tr_id": "tr7", "status": "ok", "p_late": 0.8}}


@pytest.fixture
def fake(monkeypatch) -> FakeForecaster:
    f = FakeForecaster()
    monkeypatch.setattr(server, "load_forecaster", lambda **kw: f)
    return f


def fix(unit: int, t: int) -> Fix:
    return Fix(unit, t, 0.0, 37.6, 55.75, True, 20, 90)


def test_http_contract(fake) -> None:
    with TestClient(server.app) as client:
        assert client.get("/health").json() == {"ready": True, "error": None, "units": 1}
        body = [{"unit_id": 7, "gps_time": 100, "lon": 37.6, "lat": 55.75, "location_valid": True},
                {"unit_id": 8, "gps_time": 100, "lon": 37.6, "lat": 55.75, "location_valid": True}]
        assert client.post("/fixes", json=body).json() == {"received": 2, "accepted": 1}
        assert client.get("/forecasts").json() == {"7": {"unit_id": 7, "tr_id": "tr7", "status": "ok", "p_late": 0.8}}


def test_models_missing_gives_503_with_a_hint(monkeypatch) -> None:
    def broken(**kw):
        raise FileNotFoundError("нет data/hackathon")
    monkeypatch.setattr(server, "load_forecaster", broken)
    with TestClient(server.app) as client:
        assert client.get("/health").json()["ready"] is False
        r = client.get("/forecasts")
        assert r.status_code == 503 and "data/hackathon" in r.json()["detail"]["hint"]


def _serve():
    """ml_service.server на свободном порту в фоновом потоке; yield — его адрес."""
    # Тест не должен зависеть от того, что установлено рядом: ws="none" — websockets ML-сервису
    # не нужен, loop="asyncio" — без uvloop. Оба на новых версиях Python дают DeprecationWarning,
    # а в этом проекте предупреждение — ошибка (pyproject: filterwarnings = error).
    config = uvicorn.Config(server.app, host="127.0.0.1", port=0, log_level="warning",
                            ws="none", loop="asyncio")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not (srv.started and srv.servers) and time.time() < deadline:
        time.sleep(0.05)
    port = srv.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def live_server(fake):
    yield from _serve()


@pytest.fixture
def server_without_data(monkeypatch):
    def broken(**kw):
        raise FileNotFoundError("No such file or directory: '/app/data/hackathon/train/schedule.csv'")
    monkeypatch.setattr(server, "load_forecaster", broken)
    yield from _serve()


def test_remote_client_batches_fixes_and_reads_forecasts(live_server, fake) -> None:
    client = RemoteForecaster(live_server, flush_s=0.05)
    try:
        assert client.ready
        for t in range(3):
            assert client.ingest(fix(7, 100 + t))
        deadline = time.time() + 5
        while len(fake.seen) < 3 and time.time() < deadline:
            time.sleep(0.05)
        assert fake.seen == [(7, 100, True), (7, 101, True), (7, 102, True)]
        assert client.forecasts() == {7: {"unit_id": 7, "tr_id": "tr7", "status": "ok", "p_late": 0.8}}
    finally:
        client.close()


def test_remote_client_degrades_when_the_ml_service_is_down() -> None:
    client = RemoteForecaster("http://127.0.0.1:9", flush_s=3600, timeout_s=0.5)   # отправляем вручную
    try:
        client.ingest(fix(7, 100))
        assert client.forecasts() is None and client.ready is False
        assert "недоступен" in client.error
        client.flush()                                  # не удалось отправить — отметка осталась в очереди
        assert len(client._queue) == 1
    finally:
        client.close()


def test_remote_client_reports_why_the_ml_service_is_not_ready(server_without_data) -> None:
    """Сервис жив, но без data/hackathon/: в /api/health должна попасть его причина, а не «HTTP 503»."""
    client = RemoteForecaster(server_without_data, flush_s=3600)
    try:
        assert client.ready is False
        assert "не готов" in client.error and "data/hackathon/train/schedule.csv" in client.error
    finally:
        client.close()
