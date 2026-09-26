"""Бизнес-логика живого сервиса: держит потоковое состояние, считает риск по новым событиям,
отдает текущий срез для диспетчера.

Это единственное место, где живет in-memory состояние процесса (см. ограничение MVP в
README — для прода нужен Redis/аналог). Используется тонким HTTP-слоем app/api.py; ничего
не знает про FastAPI, HTTP или JSON — только про domain-схему, engine и model.
"""
from datetime import date as _date, datetime
from typing import Iterable

import numpy as np
import pandas as pd

from app.config import ALERT_LIMIT, LATE_THRESHOLD_MIN, RISK_LEVELS
from app.domain.schema import RiskPrediction, StopEvent
from app.engine.stream_state import StreamState
from app.model.artifacts import ModelArtifacts
from app.model.explain import TOP, main_reasons, reason_text
from app.service.replay_service import hhmm


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
        rows, keys, targets = [], [], []
        finished = set()   # рейсы, которые в этой пачке дошли до конца: прогноз по ним больше не нужен
        for e in sorted(events, key=lambda x: x["fact"]):
            if e["trip_id"] not in self._artifacts.schedule:
                continue
            f, h = self._state.features(e)
            self._state.update(e)
            if h is None:
                finished.add(e["trip_id"])
                continue
            finished.discard(e["trip_id"])
            rows.append(f)
            keys.append(e)
            targets.append(h)
        if rows:
            X = pd.DataFrame(rows)
            probs = self._artifacts.predictor.predict_risk(X)
            fdelays = self._artifacts.regressor.predict_delay(X)
            # причину объясняем только там, где ее покажут диспетчеру (средний риск и выше)
            reasons = np.full((len(rows), TOP), -1)
            explain = np.flatnonzero(probs >= RISK_LEVELS[0])
            if len(explain):
                reasons[explain] = main_reasons(self._artifacts.predictor.explain(X.iloc[explain]))
            for e, f, h, prob, fd, r in zip(keys, rows, targets, probs, fdelays, reasons):
                stops, plan = self._artifacts.schedule[e["trip_id"]]
                self._latest[e["trip_id"]] = RiskPrediction(
                    trip_id=e["trip_id"],
                    route=self._artifacts.route_name.get(e["route_id"], e["route_id"]),
                    mode=self._artifacts.route_mode.get(e["route_id"], "other"),
                    stop_id=e["stop_id"], t=e["fact"],
                    delay_now=round(f["delay_now"], 1), risk=round(float(prob), 3),
                    target_stop_id=stops[h], target_plan=float(plan[h]),
                    forecast_delay=round(float(fd), 1), reason=reason_text(r))
        # удаляем после записи: иначе прогноз по раннему событию этой же пачки вернул бы
        # в тревоги рейс, который уже закончился
        for trip_id in finished:
            self._latest.pop(trip_id, None)
        return len(rows)

    def current_risk(self, limit: int = 50, min_risk: float = 0.0) -> list[RiskPrediction]:
        items = [v for v in self._latest.values() if v["risk"] >= min_risk]
        return sorted(items, key=lambda v: -v["risk"])[:limit]

    def snapshot(self, limit: int = ALERT_LIMIT) -> dict:
        """Готовый срез для дашборда: те же KPI и тот же формат тревог, что у записанного дня
        (service/replay_service.py), чтобы фронтенд рисовал их одним и тем же компонентом."""
        items = list(self._latest.values())
        high = [v for v in items if v["risk"] >= RISK_LEVELS[1]]
        late = [v for v in items if v["delay_now"] >= LATE_THRESHOLD_MIN]
        alerts = sorted((v for v in high if v["delay_now"] < LATE_THRESHOLD_MIN),
                        key=lambda v: v["delay_now"])[:limit]
        return {
            "clock": datetime.now().strftime("%H:%M"),
            "tracked": len(items),
            "kpi": [
                {"key": "onLine", "label": "рейсов под наблюдением", "value": str(len(items))},
                {"key": "high", "label": "высокий риск через 10–15 мин", "tone": "high",
                 "value": str(len(high))},
                {"key": "late", "label": "уже опаздывают", "value": str(len(late))},
                {"key": "hit", "label": "ранних тревог сбылось", "value": "—",
                 "hint": "В live-режиме проверка тревог появится, когда накопится история"},
            ],
            "alerts": [{
                "tripId": v["trip_id"],
                "route": v["route"],
                "mode": v["mode"],
                "dest": self._destination(v["trip_id"]),
                "stop": self._artifacts.stop_name.get(v["stop_id"], v["stop_id"]),
                "delay": v["delay_now"],
                "risk": int(round(v["risk"] * 100)),
                **self._forecast(v),
            } for v in alerts],
        }

    def _forecast(self, v: RiskPrediction) -> dict:
        """Те же поля прогноза, что у записанного дня (ReplayService._forecast)."""
        arrival = v["target_plan"] + v["forecast_delay"]
        out = {"currentTime": hhmm(v["t"]),
               "forecastStop": self._artifacts.stop_name.get(v["target_stop_id"], v["target_stop_id"]),
               "scheduledArrival": hhmm(v["target_plan"]), "forecastDelay": v["forecast_delay"],
               "expectedArrival": hhmm(arrival), "forecastMinutes": max(1, round(arrival - v["t"]))}
        if v["reason"]:
            out["forecastReason"] = v["reason"]
        return out

    def _destination(self, trip_id: str) -> str:
        stops, _ = self._artifacts.schedule[trip_id]
        return self._artifacts.stop_name.get(stops[-1], "")

    @property
    def schedule_size(self) -> int:
        return len(self._artifacts.schedule)
