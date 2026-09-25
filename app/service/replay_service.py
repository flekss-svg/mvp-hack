"""Воспроизведение записанного дня для диспетчерского дашборда.

Фронтенд не знает ни про рейсы, ни про интерполяцию, ни про пороги риска — он запрашивает
кадр на момент времени и рисует то, что пришло. Все, что раньше считалось в браузере
(положение машин между остановками, уровни риска, KPI, список тревог, медленные перегоны,
шкала времени), считается здесь.

Данные берутся из кэша, который готовит app/replay_build.py. Формат кэша (ReplayDay) описан
здесь, а не в сборщике: сервис не должен тянуть за собой обучение модели и sklearn.
"""
import pickle
from dataclasses import dataclass, field

import numpy as np

from app.config import (ALERT_LIMIT, REPLAY_CACHE, RISK_LEVELS, SLOW_SEG_MIN,
                        SLOW_SEG_WINDOW_MIN)

# Ключ сортировки событий: номер рейса * KEY_SPAN + время. Так все события одного рейса лежат
# подряд и весь массив глобально отсортирован — положение всех машин на момент t находится
# одним np.searchsorted, без цикла по рейсам (см. ReplayService.frame).
KEY_SPAN = 10_000.0


@dataclass
class ReplayDay:
    """Записанный день в форме, из которой кадр собирается векторно.

    События всех рейсов склеены в плоские массивы (ev_*) и отсортированы по ключу
    trip * KEY_SPAN + fact; границы рейсов — в trip_off.
    """

    date: str
    dow: int
    rain: dict
    threshold: float
    t_min: float
    t_max: float

    stop_lon: np.ndarray
    stop_lat: np.ndarray
    stop_names: list[str]

    seg_a: np.ndarray
    seg_b: np.ndarray

    ev_stop: np.ndarray      # индекс остановки
    ev_plan: np.ndarray      # плановое время, мин от начала служебных суток
    ev_fact: np.ndarray      # фактическое время
    ev_risk: np.ndarray      # риск 0..1, -1 если прогноз не выдавался
    ev_target: np.ndarray    # индекс события, в котором прогноз проверяется; -1 если нет
    ev_trip: np.ndarray      # индекс рейса
    ev_key: np.ndarray       # trip * KEY_SPAN + fact

    trip_off: np.ndarray     # (T+1,) границы событий каждого рейса
    trip_route: np.ndarray   # индекс маршрута
    trip_mode: np.ndarray    # индекс вида транспорта в modes

    route_short: list[str]
    route_long: list[str]
    modes: list[str]

    trav_t: np.ndarray       # прохождения перегонов, отсортированы по времени
    trav_seg: np.ndarray
    trav_excess: np.ndarray  # насколько дольше плана, мин

    metrics: dict = field(default_factory=dict)


HIGH = RISK_LEVELS[1]
# Окно «тревога уже должна была подтвердиться»: смотрим прогнозы, выданные 20–30 минут назад.
CHECK_FROM, CHECK_TO = 30.0, 20.0
TIMELINE_STEP_MIN = 5.0


def hhmm(minutes: float) -> str:
    """Минуты от начала служебных суток -> 'ЧЧ:ММ' (служебные сутки бывают длиннее 24 часов)."""
    m = int(minutes) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


class ReplayService:
    def __init__(self, day: ReplayDay):
        self.day = day
        self._n_trips = len(day.trip_off) - 1
        self._trip_last = day.trip_off[1:] - 1
        self._trip_first = day.trip_off[:-1]
        self._trip_targets = np.arange(self._n_trips) * KEY_SPAN
        self._ev_mode = day.trip_mode[day.ev_trip]
        # события, отсортированные по времени — чтобы проверка сбывшихся тревог смотрела
        # только на окно в 10 минут, а не на весь день
        self._by_time = np.argsort(day.ev_fact, kind="stable")
        self._time_sorted = day.ev_fact[self._by_time]

    @classmethod
    def load(cls, path=REPLAY_CACHE) -> "ReplayService":
        with open(path, "rb") as fh:
            return cls(ReplayDay(**pickle.load(fh)))

    # ---------- статика: то, что фронтенд запрашивает один раз ----------

    def day_info(self) -> dict:
        d = self.day
        return {
            "date": d.date, "dow": d.dow, "rain": d.rain, "threshold": d.threshold,
            "tMin": d.t_min, "tMax": d.t_max,
            "horizonLabel": "10–15 мин",
            "riskLevels": {"mid": RISK_LEVELS[0], "high": RISK_LEVELS[1]},
            "modes": [{"id": i, "key": m} for i, m in enumerate(d.modes)],
            "trips": self._n_trips,
            "network": {
                "stops": np.stack([d.stop_lon, d.stop_lat], axis=1).round(5).tolist(),
                "segments": np.stack([d.seg_a, d.seg_b], axis=1).tolist(),
            },
        }

    # ---------- кадр ----------

    def _alive(self, t: float, mode: int | None):
        """Индексы рейсов на линии и индексы их текущих событий на момент t."""
        pos = np.searchsorted(self.day.ev_key, self._trip_targets + t, side="right") - 1
        alive = (pos >= self._trip_first) & (t <= self.day.ev_fact[self._trip_last])
        if mode is not None:
            alive &= self.day.trip_mode == mode
        trips = np.flatnonzero(alive)
        return trips, pos[trips]

    def frame(self, t: float, mode: int | None = None, min_level: int = 0,
              trip_id: int | None = None) -> dict:
        d = self.day
        trips, idx = self._alive(t, mode)
        last = self._trip_last[trips]
        nxt = np.minimum(idx + 1, last)
        span = d.ev_fact[nxt] - d.ev_fact[idx]
        u = np.clip(np.where(span > 0, (t - d.ev_fact[idx]) / np.where(span > 0, span, 1), 0.0), 0, 1)
        a, b = d.ev_stop[idx], d.ev_stop[nxt]
        lon = d.stop_lon[a] + (d.stop_lon[b] - d.stop_lon[a]) * u
        lat = d.stop_lat[a] + (d.stop_lat[b] - d.stop_lat[a]) * u

        risk = d.ev_risk[idx]
        delay = d.ev_fact[idx] - d.ev_plan[idx]
        late = delay >= d.threshold
        # 0 низкий, 1 средний, 2 высокий, 3 — прогноз не выдается (рейс скоро завершится)
        level = np.where(risk < 0, 3, np.digitize(risk, list(RISK_LEVELS)))

        # уровень 3 — это «прогноза нет», а не «риск выше высокого», поэтому фильтр его отсекает
        keep = (level >= min_level) & (level != 3) if min_level else np.ones(len(trips), bool)
        return {
            "t": t, "clock": hhmm(t),
            "raining": bool(d.rain["level"] > 0 and d.rain["start"] <= t <= d.rain["end"]),
            "kpi": self._kpi(t, mode, risk, late, len(trips)),
            "vehicles": {
                "id": trips[keep].tolist(),
                "lon": lon[keep].round(5).tolist(),
                "lat": lat[keep].round(5).tolist(),
                "level": level[keep].astype(int).tolist(),
                "risk": np.where(risk[keep] < 0, -1, (risk[keep] * 100).round()).astype(int).tolist(),
                "late": late[keep].astype(int).tolist(),
            },
            "slowSegments": self._slow_segments(t),
            "alerts": self._alerts(trips, idx, risk, delay),
            # карточка выбранного рейса едет вместе с кадром: один запрос на такт
            "trip": self.trip(trip_id, t) if trip_id is not None else None,
        }

    def _kpi(self, t, mode, risk, late, on_line) -> list[dict]:
        hit = self._hit_rate(t, mode)
        return [
            {"key": "onLine", "label": "на линии", "value": str(on_line)},
            {"key": "high", "label": "высокий риск через 10–15 мин", "tone": "high",
             "value": str(int((risk >= HIGH).sum()))},
            {"key": "late", "label": "уже опаздывают", "value": str(int(late.sum()))},
            {"key": "hit", "label": "ранних тревог сбылось",
             "value": f"{round(100 * hit[0] / hit[1])}%" if hit else "—",
             "hint": (f"Из {hit[1]} тревог, выданных 20–30 минут назад машинам без опоздания, "
                      f"сбылось {hit[0]}") if hit else "Пока недостаточно тревог для проверки"},
        ]

    def _hit_rate(self, t: float, mode: int | None):
        """Тревоги, выданные 20–30 минут назад машинам, которые тогда шли по графику:
        сколько из них уже подтвердилось опозданием. Честная проверка прямо на глазах у
        диспетчера — без нее высокий риск выглядит просто красной точкой."""
        d = self.day
        lo, hi = np.searchsorted(self._time_sorted, [t - CHECK_FROM, t - CHECK_TO])
        ev = self._by_time[lo:hi]
        if mode is not None:
            ev = ev[self._ev_mode[ev] == mode]
        tgt = d.ev_target[ev]
        ok = (d.ev_risk[ev] >= HIGH) & (tgt >= 0) & (d.ev_fact[ev] - d.ev_plan[ev] < d.threshold)
        ev, tgt = ev[ok], tgt[ok]
        done = d.ev_fact[tgt] <= t
        tgt = tgt[done]
        if len(tgt) < 5:
            return None
        return int(((d.ev_fact[tgt] - d.ev_plan[tgt]) >= d.threshold).sum()), len(tgt)

    def _slow_segments(self, t: float) -> list[list]:
        d = self.day
        lo, hi = np.searchsorted(d.trav_t, [t - SLOW_SEG_WINDOW_MIN, t])
        if hi <= lo:
            return []
        seg, ex = d.trav_seg[lo:hi], d.trav_excess[lo:hi]
        n = len(d.seg_a)
        total = np.bincount(seg, weights=ex, minlength=n)
        count = np.bincount(seg, minlength=n)
        mean = np.divide(total, count, out=np.zeros(n), where=count > 0)
        hit = np.flatnonzero(mean >= SLOW_SEG_MIN[0])
        # [индекс перегона, ступень (0 — медленнее плана, 1 — сильно), среднее превышение, мин]
        return [[int(s), int(mean[s] >= SLOW_SEG_MIN[1]), round(float(mean[s]), 1)] for s in hit]

    def _alerts(self, trips, idx, risk, delay) -> list[dict]:
        """Машины, которые сейчас идут по графику, но опоздают через 10–15 минут — ради них
        и нужен прогноз. Сортировка по текущему отклонению: сверху те, у кого все выглядит
        благополучно, — их диспетчер без модели не увидит вовсе."""
        d = self.day
        m = np.flatnonzero((risk >= HIGH) & (delay < d.threshold))
        m = m[np.argsort(delay[m], kind="stable")][:ALERT_LIMIT]
        out = []
        for i in m:
            trip, ev = int(trips[i]), int(idx[i])
            r = d.trip_route[trip]
            out.append({
                "tripId": trip,
                "route": d.route_short[r],
                "mode": d.modes[d.trip_mode[trip]],
                "dest": d.stop_names[d.ev_stop[self._trip_last[trip]]],
                "stop": d.stop_names[d.ev_stop[ev]],
                "delay": round(float(delay[i]), 1),
                "risk": int(round(float(risk[i]) * 100)),
            })
        return out

    # ---------- шкала времени ----------

    def timeline(self, mode: int | None = None) -> dict:
        d = self.day
        bins = np.arange(np.floor(d.t_min / TIMELINE_STEP_MIN) * TIMELINE_STEP_MIN,
                         d.t_max, TIMELINE_STEP_MIN)
        counts = []
        for b in bins:
            trips, idx = self._alive(float(b), mode)
            counts.append(int((d.ev_risk[idx] >= HIGH).sum()))
        hours = np.arange(np.ceil(d.t_min / 60), d.t_max / 60)
        return {
            "tMin": d.t_min, "tMax": d.t_max,
            "bins": [{"t": float(b), "high": c} for b, c in zip(bins, counts)],
            "ticks": [{"t": float(h * 60), "label": hhmm(h * 60)} for h in hours],
            "rain": d.rain if d.rain["level"] > 0 else None,
        }

    # ---------- карточка рейса ----------

    def trip(self, trip_id: int, t: float) -> dict:
        d = self.day
        if not 0 <= trip_id < self._n_trips:
            return {"found": False}
        first, last = int(self._trip_first[trip_id]), int(self._trip_last[trip_id])
        r = d.trip_route[trip_id]
        head = {"route": d.route_short[r], "routeName": d.route_long[r],
                "mode": d.modes[d.trip_mode[trip_id]]}
        if not (d.ev_fact[first] <= t <= d.ev_fact[last]):
            return {"found": True, "onLine": False, **head}

        ev = first + int(np.searchsorted(d.ev_fact[first:last + 1], t, side="right")) - 1
        risk = float(d.ev_risk[ev])
        delay = float(d.ev_fact[ev] - d.ev_plan[ev])
        outcome = None
        tgt = int(d.ev_target[ev])
        if tgt >= 0 and d.ev_fact[tgt] <= t:
            gap = float(d.ev_fact[tgt] - d.ev_plan[tgt])
            outcome = {"late": gap >= d.threshold, "delay": round(gap, 1)}
        return {
            "found": True, "onLine": True, **head,
            "stop": d.stop_names[d.ev_stop[ev]],
            "delay": round(delay, 1),
            "risk": int(round(risk * 100)) if risk >= 0 else None,
            "level": 3 if risk < 0 else int(np.digitize(risk, list(RISK_LEVELS))),
            "outcome": outcome,
            "next": [{"stop": d.stop_names[d.ev_stop[j]], "plan": hhmm(d.ev_plan[j])}
                     for j in range(ev + 1, min(last + 1, ev + 5))],
        }
