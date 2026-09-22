"""Веб-сервис предиктора: принимает поток событий, отдает риск по машинам.

Запуск:  uvicorn api:app --reload   (из папки src)

POST /events   — пачка событий «машина прошла остановку» (после ingest.py)
GET  /risk     — текущий риск по всем активным рейсам, отсортирован по убыванию
GET  /health
"""
import pickle
from datetime import date as _date

import pandas as pd
from catboost import CatBoostClassifier
from fastapi import FastAPI
from pydantic import BaseModel

from config import MODELS, PROC
from features import FEATURES, StreamState, load_schedule_index

app = FastAPI(title="Предиктор задержек наземного транспорта")

_model = CatBoostClassifier()
_model.load_model(str(MODELS / "delay_catboost.cbm"))
_schedule = load_schedule_index()
with open(MODELS / "hist_profile.pkl", "rb") as fh:
    _hist = pickle.load(fh)
_routes = pd.read_parquet(PROC / "routes.parquet")
_route_mode = dict(zip(_routes.route_id, _routes["mode"]))
_route_name = dict(zip(_routes.route_id, _routes.route_short_name))

_state = StreamState(_schedule, _hist, _route_mode)
_d = _date.today()
_state.set_context(dow=_d.weekday(), weekend=int(_d.weekday() >= 5), holiday=0, rain=0.0)
_latest = {}  # trip_id -> последний прогноз


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
    return {"ok": True, "trips_in_schedule": len(_schedule)}


@app.post("/context")
def set_context(c: Context):
    _state.set_context(rain=c.rain, holiday=c.holiday)
    return {"ok": True}


@app.post("/events")
def events(batch: list[Event]):
    rows, keys = [], []
    for ev in sorted(batch, key=lambda x: x.fact):
        e = ev.model_dump()
        if e["trip_id"] not in _schedule:
            continue
        f, h = _state.features(e)
        _state.update(e)
        if h is None:
            _latest.pop(e["trip_id"], None)
            continue
        rows.append(f)
        keys.append(e)
    if rows:
        p = _model.predict_proba(pd.DataFrame(rows, columns=FEATURES).astype("float32"))[:, 1]
        for e, f, prob in zip(keys, rows, p):
            _latest[e["trip_id"]] = {
                "trip_id": e["trip_id"], "route": _route_name.get(e["route_id"], e["route_id"]),
                "stop_id": e["stop_id"], "t": e["fact"], "delay_now": round(f["delay_now"], 1),
                "risk": round(float(prob), 3)}
    return {"accepted": len(batch), "scored": len(rows)}


@app.get("/risk")
def risk(limit: int = 50, min_risk: float = 0.0):
    items = [v for v in _latest.values() if v["risk"] >= min_risk]
    return sorted(items, key=lambda v: -v["risk"])[:limit]
