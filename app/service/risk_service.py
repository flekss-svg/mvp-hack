"""Бизнес-логика живого сервиса: держит потоковое состояние, считает риск по новым событиям,
отдает текущий срез для диспетчера.

Это единственное место, где живет in-memory состояние процесса (см. ограничение MVP в
README — для прода нужен Redis/аналог). Используется тонким HTTP-слоем app/api.py; ничего
не знает про FastAPI, HTTP или JSON — только про domain-схему, engine и model.
"""
from datetime import date as _date
from typing import Iterable

import pandas as pd

from app.domain.schema import RiskPrediction, StopEvent
from app.engine.stream_state import StreamState
from app.model.artifacts import ModelArtifacts


class RiskService:
    def __init__(self, artifacts: ModelArtifacts):
        self._artifacts = artifacts
        self._state = StreamState(artifacts.schedule, artifacts.hist_profile, artifacts.route_mode)
        today = _date.today()
        self._state.set_context(dow=today.weekday(), weekend=int(today.weekday() >= 5), holiday=0, rain=0.0)
        self._latest: dict[str, RiskPrediction] = {}

    def set_context(self, rain: float = 0.0, holiday: int = 0) -> None:
        self._state.set_context(rain=rain, holiday=holiday)

    def ingest_events(self, events: Iterable[StopEvent]) -> int:
        """Принять пачку событий «машина прошла остановку», обновить риск по затронутым
        рейсам. Возвращает число событий, для которых был посчитан прогноз."""
        rows, keys = [], []
        for e in sorted(events, key=lambda x: x["fact"]):
            if e["trip_id"] not in self._artifacts.schedule:
                continue
            f, h = self._state.features(e)
            self._state.update(e)
            if h is None:
                self._latest.pop(e["trip_id"], None)
                continue
            rows.append(f)
            keys.append(e)
        if rows:
            probs = self._artifacts.predictor.predict_risk(pd.DataFrame(rows))
            for e, f, prob in zip(keys, rows, probs):
                self._latest[e["trip_id"]] = RiskPrediction(
                    trip_id=e["trip_id"],
                    route=self._artifacts.route_name.get(e["route_id"], e["route_id"]),
                    stop_id=e["stop_id"], t=e["fact"],
                    delay_now=round(f["delay_now"], 1), risk=round(float(prob), 3))
        return len(rows)

    def current_risk(self, limit: int = 50, min_risk: float = 0.0) -> list[RiskPrediction]:
        items = [v for v in self._latest.values() if v["risk"] >= min_risk]
        return sorted(items, key=lambda v: -v["risk"])[:limit]

    @property
    def schedule_size(self) -> int:
        return len(self._artifacts.schedule)
