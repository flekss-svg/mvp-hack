"""Веб-сервис предиктора: тонкий HTTP-слой (FastAPI) поверх бизнес-логики в service/.

Запуск (из корня репозитория):
    uvicorn app.api:app --reload

POST /events   — пачка событий «машина прошла остановку» (после ingest-адаптера)
GET  /risk     — текущий риск по всем активным рейсам, отсортирован по убыванию
POST /context  — погода/праздник на сегодня
GET  /health

Дашборд (dashboard/index.html) отдается статикой на /dashboard/ и в режиме "Live" сам
опрашивает GET /risk — так дашборд связан с бэкендом напрямую, а не только через
сгенерированный заранее data.json (см. app/dashboard_export.py).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import DASH
from app.model.artifacts import ModelArtifacts
from app.service.risk_service import RiskService

app = FastAPI(title="Предиктор задержек наземного транспорта")

# Дашборд может открываться отдельно (file://, другой порт) и стучаться в API кросс-доменно —
# для MVP это ок, для прода стоит сузить allow_origins до конкретного адреса дашборда.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_service = RiskService(ModelArtifacts.load())


class Event(BaseModel):
    trip_id: str
    route_id: str
    direction_id: str
    k: int
    stop_id: str
    plan: float
    fact: float


class Context(BaseModel):
    rain: float = 0.0
    holiday: int = 0


@app.get("/health")
def health():
    return {"ok": True, "trips_in_schedule": _service.schedule_size}


@app.post("/context")
def set_context(c: Context):
    _service.set_context(rain=c.rain, holiday=c.holiday)
    return {"ok": True}


@app.post("/events")
def events(batch: list[Event]):
    rows = [e.model_dump() for e in batch]
    scored = _service.ingest_events(rows)
    return {"accepted": len(batch), "scored": scored}


@app.get("/risk")
def risk(limit: int = 50, min_risk: float = 0.0):
    return _service.current_risk(limit=limit, min_risk=min_risk)


if DASH.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASH), html=True), name="dashboard")
