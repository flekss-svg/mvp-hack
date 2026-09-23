"""Потоковый расчет признаков.

Один и тот же класс StreamState используется и для обучения (прогон истории в run_day),
и в живом сервисе (service/risk_service.py). Так признаки в обучении и в проде считаются
одинаково — без расхождений.

Этот модуль не знает, откуда взялись события (симулятор или реальная телематика) и какая
ML-библиотека обучается на его выходе — он оперирует только канонической схемой из
domain/schema.py (StopEvent) и отдает чистые числовые признаки (FEATURES).

Событие на входе: машина прошла остановку
    trip_id, route_id, direction_id, k (номер остановки в рейсе), stop_id, plan, fact
где plan/fact — минуты от начала служебных суток.
"""
import math
from collections import defaultdict, deque

import numpy as np
import pandas as pd

from app.config import HORIZON_MIN, LATE_THRESHOLD_MIN
from app.data_sources import processed_repository as repo
from app.engine.feature_definitions import FEATURES

H_TARGET = (HORIZON_MIN[0] + HORIZON_MIN[1]) / 2  # 12.5 мин: целевая точка прогноза
RECENT_TTL = 20.0     # информация о перегоне «живет» 20 минут
RECENT_TAU = 10.0     # и затухает с этой постоянной


def load_schedule_index(stop_times: pd.DataFrame | None = None) -> dict:
    """trip_id -> (stops[], plan[]) из планового расписания (статичные данные).

    Если stop_times не передан, читается через processed_repository (data/processed/stop_times.parquet).
    """
    st = stop_times if stop_times is not None else repo.read_stop_times()
    g = st.groupby("trip_id", sort=False)
    stops, plan = g["stop_id"].apply(list), g["arr_min"].apply(list)
    return {t: (stops[t], plan[t]) for t in stops.index}


class StreamState:
    def __init__(self, schedule, hist_profile=None, route_mode=None):
        self.schedule = schedule                  # trip_id -> (stops, plan)
        self.hist = hist_profile or {}            # (seg, hour) -> средний избыток времени хода
        self.route_mode = route_mode or {}
        self.seg_recent = {}                      # seg -> (ewm избытка, время последнего прохода)
        self.trip_hist = defaultdict(lambda: deque(maxlen=4))  # trip -> [(k, fact, plan)]
        self.last_pass = {}                       # (route, dir, stop) -> (fact, plan)
        self.route_recent = {}                    # (route, dir) -> (ewm задержки, время)
        self.context = dict(dow=0, weekend=0, holiday=0, rain=0.0)

    def set_context(self, **kw):
        self.context.update(kw)

    def _recent(self, seg, t):
        v = self.seg_recent.get(seg)
        if v is None or t - v[1] > RECENT_TTL:
            return None
        return v[0] * math.exp(-(t - v[1]) / RECENT_TAU)

    def features(self, e):
        """Признаки для события e (до обновления состояния). Возвращает (dict, индекс цели)."""
        stops, plan = self.schedule[e["trip_id"]]
        k, t = e["k"], e["fact"]
        n = len(stops)
        delay = t - e["plan"]

        # точка прогноза: первая остановка, запланированная через >= 12.5 минут
        h = k + 1
        while h < n and plan[h] - plan[k] < H_TARGET:
            h += 1
        if h >= n or plan[h] - plan[k] > HORIZON_MIN[1] + 5:
            h = None  # рейс закончится раньше горизонта — прогноз не нужен

        hist = self.trip_hist[e["trip_id"]]
        if hist:
            k0, f0, p0 = hist[0]
            d_delay_3 = delay - (f0 - p0)
            run_ratio_3 = (t - f0) / max(e["plan"] - p0, 0.5)
        else:
            d_delay_3, run_ratio_3 = np.nan, np.nan

        lp = self.last_pass.get((e["route_id"], e["direction_id"], e["stop_id"]))
        if lp is not None and 0 < e["plan"] - lp[1] < 30:
            lead_delay = lp[0] - lp[1]
            lead_headway_dev = (t - lp[0]) - (e["plan"] - lp[1])
        else:
            lead_delay, lead_headway_dev = np.nan, np.nan

        rr = self.route_recent.get((e["route_id"], e["direction_id"]))
        route_recent_delay = rr[0] if rr is not None and t - rr[1] < 20 else np.nan

        end = h if h is not None else n - 1
        rs, rmax, rn, hs = 0.0, 0.0, 0, 0.0
        for j in range(k + 1, end + 1):
            seg = (stops[j - 1], stops[j])
            r = self._recent(seg, t)
            if r is not None:
                rs += r
                rmax = max(rmax, r)
                rn += 1
            hs += self.hist.get((seg, int(plan[j - 1] // 60) % 24), 0.0)

        c = self.context
        f = dict(
            delay_now=delay, d_delay_3=d_delay_3, run_ratio_3=run_ratio_3,
            lead_delay=lead_delay, lead_headway_dev=lead_headway_dev,
            route_recent_delay=route_recent_delay,
            ahead_recent_sum=rs, ahead_recent_max=rmax, ahead_recent_n=rn, ahead_hist_sum=hs,
            ahead_plan_min=plan[end] - plan[k], ahead_n_segs=end - k,
            stops_left=n - 1 - k, progress=k / max(n - 1, 1),
            hour=int(e["plan"] // 60) % 24, dow=c["dow"], weekend=c["weekend"],
            holiday=c["holiday"], rain=c["rain"](t) if callable(c["rain"]) else c["rain"],
            is_tram=int(self.route_mode.get(e["route_id"]) == "tram"),
        )
        return f, h

    def update(self, e):
        stops, plan = self.schedule[e["trip_id"]]
        k, t = e["k"], e["fact"]
        hist = self.trip_hist[e["trip_id"]]
        if hist and hist[-1][0] == k - 1:
            _, f_prev, p_prev = hist[-1]
            excess = (t - f_prev) - (e["plan"] - p_prev)
            seg = (stops[k - 1], stops[k])
            old = self._recent(seg, t)
            self.seg_recent[seg] = (excess if old is None else 0.5 * old + 0.5 * excess, t)
        hist.append((k, t, e["plan"]))
        self.last_pass[(e["route_id"], e["direction_id"], e["stop_id"])] = (t, e["plan"])
        key = (e["route_id"], e["direction_id"])
        rr = self.route_recent.get(key)
        d = t - e["plan"]
        self.route_recent[key] = (d if rr is None else 0.8 * rr[0] + 0.2 * d, t)
        if k == len(stops) - 1:
            self.trip_hist.pop(e["trip_id"], None)


def build_hist_profile(fact_days):
    """Средний избыток времени хода по перегону и часу — по «профильным» дням."""
    parts = []
    for df in fact_days:
        df = df.sort_values(["trip_id", "k"])
        prev_stop = df.groupby("trip_id")["stop_id"].shift()
        ex = df["fact"].diff() - df["plan"].diff()
        ok = prev_stop.notna()
        parts.append(pd.DataFrame({"a": prev_stop[ok], "b": df.loc[ok, "stop_id"],
                                   "hour": (df.loc[ok, "plan"] // 60 % 24).astype(int),
                                   "ex": ex[ok]}))
    p = pd.concat(parts).groupby(["a", "b", "hour"])["ex"].mean()
    return {((a, b), h): v for (a, b, h), v in p.items()}


def run_day(state: StreamState, df: pd.DataFrame, sample=1.0, rng=None, on_row=None):
    """Прогоняет день событий (в канонической схеме STOP_EVENT_COLUMNS) через поток.
    Возвращает таблицу признаков (X, колонки FEATURES) + метаданные и цель (M)."""
    df = df.sort_values("fact", kind="stable")
    cols = ["trip_id", "route_id", "direction_id", "k", "stop_id", "plan", "fact"]
    rows, meta = [], []
    for rec in df[cols].itertuples(index=False):
        e = rec._asdict()
        f, h = state.features(e)
        if h is not None and (sample >= 1 or rng.random() < sample):
            rows.append(f)
            meta.append((e["trip_id"], e["k"], h, e["fact"], e["stop_id"], e["route_id"]))
        if on_row is not None:
            on_row(e, f, h)
        state.update(e)
    X = pd.DataFrame(rows, columns=FEATURES).astype("float32")
    M = pd.DataFrame(meta, columns=["trip_id", "k", "h", "t", "stop_id", "route_id"])
    # цель: задержка в точке прогноза (известна только постфактум — для обучения)
    d = df.set_index(["trip_id", "k"])
    fut = d["fact"] - d["plan"]
    M["delay_future"] = fut.reindex(pd.MultiIndex.from_arrays([M.trip_id, M.h])).to_numpy()
    M["y"] = (M["delay_future"] >= LATE_THRESHOLD_MIN).astype(int)
    return X, M
