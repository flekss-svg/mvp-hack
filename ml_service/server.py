"""FastAPI-сервис прогнозирования задержки по живой NDTP-телеметрии."""

import math
import os
from collections import defaultdict, deque
from pathlib import Path
from threading import RLock

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from fastapi import FastAPI
from pydantic import BaseModel

from ml_service.ids import unit_id_for_trip
from scripts.telemetry_features import build, haversine, load_plan

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("HACKATHON_DATA_DIR", ROOT / "data" / "hackathon"))
MODEL_PATH = Path(os.environ.get("ML_MODEL_PATH", ROOT / "models" / "hackathon_v2_catboost.cbm"))
PLAN_TZ_OFFSET_S = int(os.environ.get("NDTP_PLAN_TZ_OFFSET_S", "0"))
HISTORY_S = 900
WARMUP_S = 600
TARGET_HORIZON_S = 750


class TelemetryPing(BaseModel):
    unit_id: int
    event_time: int
    lon: float
    lat: float
    speed: float = 0.0
    location_valid: bool = True
    tr_id: str | None = None


class ForecastEngine:
    def __init__(self, data_root: Path = DATA_ROOT, model_path: Path = MODEL_PATH):
        self.data_root = data_root
        self.model_path = model_path
        self.model: CatBoostRegressor | None = None
        self.model_error: str | None = None
        self.data_error: str | None = None
        self.feature_names: list[str] = []
        self.plan = pd.DataFrame(columns=["tt_action_item_id", "tr_id", "t_plan", "s_lat", "s_lon"])
        self.plan_by_trip: dict[str, pd.DataFrame] = {}
        self.unit_to_trip: dict[int, str] = {}
        self.history: dict[str, deque[dict]] = defaultdict(deque)
        self._lock = RLock()
        self._load_model()
        self.reload_data()

    @property
    def ready(self) -> bool:
        return self.model is not None

    @property
    def data_ready(self) -> bool:
        return bool(self.plan_by_trip)

    def _load_model(self) -> None:
        try:
            model = CatBoostRegressor()
            model.load_model(str(self.model_path))
            self.model = model
            self.feature_names = list(model.feature_names_)
            self.model_error = None
        except Exception as exc:  # noqa: BLE001 - причина нужна в /health
            self.model = None
            self.model_error = f"{type(exc).__name__}: {exc}"

    def reload_data(self) -> None:
        plans = []
        mapping: dict[int, str] = {}
        errors = []
        variants = (
            ("validate", "schedule_plan.csv"),
            ("test", "schedule.csv"),
            ("train", "schedule.csv"),
        )
        for part, schedule_name in variants:
            schedule_path = self.data_root / part / schedule_name
            traffic_path = self.data_root / part / "traffic.csv"
            if schedule_path.exists():
                try:
                    frame = load_plan(schedule_path)
                    frame["t_plan"] = frame["t_plan"] + PLAN_TZ_OFFSET_S
                    plans.append(frame)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{schedule_path}: {exc}")
            if traffic_path.exists():
                try:
                    for chunk in pd.read_csv(traffic_path, usecols=["tr_id"], dtype=str, chunksize=250_000):
                        for trip_id in chunk["tr_id"].dropna().unique():
                            mapping[unit_id_for_trip(trip_id)] = trip_id
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{traffic_path}: {exc}")
        if plans:
            self.plan = pd.concat(plans, ignore_index=True).drop_duplicates(
                ["tr_id", "tt_action_item_id", "t_plan"]
            )
            self.plan_by_trip = {
                str(trip_id): group.reset_index(drop=True)
                for trip_id, group in self.plan.groupby("tr_id", sort=False)
            }
        self.unit_to_trip = mapping
        self.data_error = "; ".join(errors) or (None if plans else f"нет расписаний в {self.data_root}")

    def predict(self, ping: TelemetryPing) -> dict:
        with self._lock:
            trip_id = ping.tr_id or self.unit_to_trip.get(ping.unit_id)
            if trip_id is None:
                return self._pending(ping, "unit_id не сопоставлен с tr_id")
            trip_id = str(trip_id)
            plan = self.plan_by_trip.get(trip_id)
            if plan is None or plan.empty:
                return self._pending(ping, "для рейса нет планового расписания", trip_id)

            history = self.history[trip_id]
            history.append({
                "t": int(ping.event_time),
                "lat": float(ping.lat),
                "lon": float(ping.lon),
                "speed": float(ping.speed),
                "valid": bool(ping.location_valid),
            })
            cutoff = ping.event_time - HISTORY_S
            while history and history[0]["t"] < cutoff:
                history.popleft()
            if len(history) < 2 or history[-1]["t"] - history[0]["t"] < WARMUP_S:
                return self._pending(ping, "накапливается 10-минутное окно телеметрии", trip_id)
            if self.model is None:
                return self._pending(ping, self.model_error or "модель не загружена", trip_id)

            current_index = self._nearest_stop_index(plan, ping.lat, ping.lon)
            current_plan_s = int(plan.iloc[current_index]["t_plan"])
            desired = max(int(ping.event_time) + TARGET_HORIZON_S, current_plan_s + TARGET_HORIZON_S)
            future = plan.index[plan["t_plan"] >= desired].tolist()
            if not future:
                return self._pending(ping, "до конца рейса меньше 10–15 минут", trip_id)
            target_index = future[0]
            target = plan.loc[target_index]

            points = pd.DataFrame([{
                "sample_id": f"live-{ping.unit_id}-{ping.event_time}",
                "tr_id": trip_id,
                "T_s": int(ping.event_time),
                "tgt_s": int(target["t_plan"]),
                "target_stop_id": str(target["tt_action_item_id"]),
                "cur_dev_s": float(ping.event_time - current_plan_s),
            }])
            telemetry = {
                trip_id: {
                    "t": np.array([row["t"] for row in history], dtype=np.int64),
                    "lat": np.array([row["lat"] for row in history], dtype=float),
                    "lon": np.array([row["lon"] for row in history], dtype=float),
                    "speed": np.array([row["speed"] for row in history], dtype=float),
                    "valid": np.array([row["valid"] for row in history], dtype=bool),
                }
            }
            features = build(points, telemetry, self.plan)
            features["cur_dev_s"] = points["cur_dev_s"]
            features["horizon_s"] = points["tgt_s"] - points["T_s"]
            features["tgt_min_of_day"] = (points["tgt_s"] % 86400) / 60
            features = features.reindex(columns=self.feature_names)
            target_delay_s = float(self.model.predict(features)[0])
            risk = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, (target_delay_s - 180.0) / 60.0))))
            return {
                "ready": True,
                "predictionReady": True,
                "mode": "service",
                "unitId": ping.unit_id,
                "tripId": trip_id,
                "targetStopId": str(target["tt_action_item_id"]),
                "horizonSec": int(target["t_plan"] - ping.event_time),
                "currentDelaySec": round(float(ping.event_time - current_plan_s), 1),
                "targetDelaySec": round(target_delay_s, 1),
                "risk": round(risk, 4),
            }

    @staticmethod
    def _nearest_stop_index(plan: pd.DataFrame, lat: float, lon: float) -> int:
        distances = haversine(
            np.full(len(plan), lat),
            np.full(len(plan), lon),
            plan["s_lat"].to_numpy(float),
            plan["s_lon"].to_numpy(float),
        )
        return int(np.nanargmin(distances))

    @staticmethod
    def _pending(ping: TelemetryPing, reason: str, trip_id: str | None = None) -> dict:
        return {
            "ready": True,
            "predictionReady": False,
            "mode": "service",
            "unitId": ping.unit_id,
            "tripId": trip_id,
            "reason": reason,
        }


engine = ForecastEngine()
app = FastAPI(title="ML-сервис прогноза задержек", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {
        "ready": engine.ready,
        "mode": "service",
        "dataReady": engine.data_ready,
        "model": str(engine.model_path),
        "error": engine.model_error,
        "dataError": engine.data_error,
    }


@app.post("/predict")
def predict(ping: TelemetryPing) -> dict:
    return engine.predict(ping)
