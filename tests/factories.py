from __future__ import annotations

import numpy as np

from app.replay_build import KEY_SPAN, ReplayDay


def make_replay_day() -> ReplayDay:
    """Small deterministic day shared by unit, API and browser tests."""
    ev_trip = np.array([0, 0], dtype=np.int32)
    ev_fact = np.array([480.0, 490.0], dtype=np.float64)
    return ReplayDay(
        date="2026-09-03",
        dow=3,
        rain={"level": 0.0, "start": 0.0, "end": 0.0},
        threshold=3.0,
        t_min=480.0,
        t_max=490.0,
        stop_lon=np.array([37.61, 37.62], dtype=np.float32),
        stop_lat=np.array([55.75, 55.76], dtype=np.float32),
        stop_names=["Начальная", "Конечная"],
        seg_a=np.array([0], dtype=np.int32),
        seg_b=np.array([1], dtype=np.int32),
        ev_stop=np.array([0, 1], dtype=np.int32),
        ev_plan=np.array([480.0, 487.0], dtype=np.float64),
        ev_fact=ev_fact,
        ev_risk=np.array([0.8, -1.0], dtype=np.float32),
        ev_target=np.array([1, -1], dtype=np.int64),
        ev_trip=ev_trip,
        ev_key=ev_trip * KEY_SPAN + ev_fact,
        trip_off=np.array([0, 2], dtype=np.int64),
        trip_route=np.array([0], dtype=np.int32),
        trip_mode=np.array([0], dtype=np.int32),
        route_short=["42"],
        route_long=["Тестовый маршрут"],
        modes=["bus", "tram", "trolley", "other"],
        trav_t=np.array([490.0], dtype=np.float64),
        trav_seg=np.array([0], dtype=np.int32),
        trav_excess=np.array([3.0], dtype=np.float32),
    )


class FakeLiveService:
    schedule_size = 1

    def __init__(self) -> None:
        self.context = {"rain": 0.0, "holiday": 0}

    def snapshot(self) -> dict:
        return {"clock": "08:05", "tracked": 1, "kpi": [], "alerts": []}

    def ingest_events(self, events: list[dict]) -> int:
        return len(events)

    def set_context(self, rain: float, holiday: int) -> None:
        self.context = {"rain": rain, "holiday": holiday}

    def current_risk(self, limit: int, min_risk: float) -> list[dict]:
        if not limit or min_risk > 0.8:
            return []
        return [{"trip_id": "trip-1", "risk": 0.8}]
