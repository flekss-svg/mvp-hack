"""Прогноз задержек по живому потоку отметок (NDTP) на моделях хакатона.

Поток NDTP отдает только «машина X в момент t была в точке (lat, lon)». Для прогноза нужны:
  * сопоставление unit_id -> tr_id: по таблице из данных хакатона (взаимно однозначные столбцы
    traffic.csv), а для незнакомого терминала — по треку (map matching, ml_service/map_matching.py);
  * расписание этого ТС (плановые времена и координаты остановок);
  * история отметок за последние минуты — приемник хранит только последнюю, поэтому копим здесь.

Прогноз строится так же, как в обучении, на момент T — «сейчас» потока: самая свежая метка среди всех
машин (для реального потока это часы, для проигрывателя — его время). Не время последней отметки
самой машины: у молчащей машины окно прогноза должно двигаться вместе с часами.
Целевая остановка — первая, плановое прибытие на которую попадает в окно (T+10 мин, T+15 мин]; в
разметке хакатона это правило совпадает в 97.6% точек. cur_dev_s (в потоке подсказки нет) оценивает
ml_service/cur_dev.py; признаки считает ml_service/features.py (тот же код, что при обучении); модели
обучены на наших оценках cur_dev_s (scripts/model_online.py).

Модуль ничего не знает про HTTP и про формат дашборда: возвращает числа и тексты причин.
Время считаем в «плановой» шкале: секунды от эпохи, в которых записаны плановые времена в CSV.
Если терминалы шлют настоящее UTC, а расписание записано по местному времени, задайте tz_offset_s
(сколько секунд прибавить к gps_time, чтобы попасть в шкалу расписания).
"""
import threading
import time
from collections import deque

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from .cur_dev import estimate_cur_dev_detail
from .features import DATA, full_features, load_plan
from .map_matching import CONFIRM, TripIndex, match
from .models import ONLINE_CLASSIFIER_PATH, ONLINE_REGRESSOR_PATH, load_classifier, predict_class_probs
from .reasons import explain

HORIZON_S = (600, 900)     # целевая остановка: плановое прибытие в (T+10 мин, T+15 мин]
HISTORY_S = 3600           # сколько истории отметок держим: хватает и признакам (10 мин), и cur_dev
MIN_VALID_PINGS = 2
STALE_S = 300              # машина молчит дольше (по часам потока) — прогноз не выдаем
MAX_RECOMPUTE = 8          # сколько машин пересчитать за один запрос: остальные отдаются из кэша
MATCH_EVERY_S = 60         # как часто (по часам потока) пробовать сопоставить незнакомую машину с рейсом
MAX_MATCH = 5              # сколько незнакомых машин сопоставлять за один запрос

_PARTS = (("train", "schedule.csv"), ("test", "schedule.csv"), ("validate", "schedule_plan.csv"))


def load_assets(data=DATA):
    """(расписание, названия остановок, unit_id -> tr_id) из файлов организаторов.

    Факт (time_fact_begin) отбрасывается при чтении расписания (load_plan)."""
    plans, names, pairs = [], {}, []
    for part, sched in _PARTS:
        plans.append(load_plan(data / part / sched))
        addr = pd.read_csv(data / part / sched, usecols=["tt_action_item_id", "building_address"], dtype=str)
        names.update(zip(addr["tt_action_item_id"], addr["building_address"].fillna("")))
        pairs.append(pd.read_csv(data / part / "traffic.csv", usecols=["tr_id", "unit_id"], dtype=str)
                     .dropna().drop_duplicates())
    plan = (pd.concat(plans).drop_duplicates("tt_action_item_id").sort_values(["tr_id", "t_plan"])
            .reset_index(drop=True))
    pairs = pd.concat(pairs).drop_duplicates()
    unit_to_tr = {int(float(u)): t for u, t in zip(pairs["unit_id"], pairs["tr_id"])}
    return plan, names, unit_to_tr


class LiveForecaster:
    def __init__(self, plan: pd.DataFrame, unit_to_tr: dict, stop_names: dict, regressor: CatBoostRegressor,
                 classifier, *, tz_offset_s: int = 0, min_interval_s: float = 5.0, clock=time.monotonic,
                 max_recompute: int = MAX_RECOMPUTE):
        self._plan_by_tr = {tr: g.reset_index(drop=True) for tr, g in plan.groupby("tr_id", sort=False)}
        self._table = {u: tr for u, tr in unit_to_tr.items() if tr in self._plan_by_tr}
        self._unit_to_tr = dict(self._table)         # текущие привязки: таблица + найденные по треку
        self._tr_to_unit = {tr: u for u, tr in self._unit_to_tr.items()}
        self._index = TripIndex(plan)
        self._by_track: set = set()                  # unit_id, привязанные по треку
        self._unknown: dict = {}                     # unit_id -> deque отметок незнакомой машины
        self._streak: dict = {}                      # unit_id -> (tr_id последнего совпадения, сколько подряд)
        self._next_try: dict = {}                    # unit_id -> время потока следующей попытки
        self._names, self._reg, self._clf = stop_names, regressor, classifier
        self._features = list(regressor.feature_names_)
        self._tz, self._min_interval, self._clock = tz_offset_s, min_interval_s, clock
        self._max_recompute = max_recompute
        self._stream_t = None       # «сейчас» потока: самая свежая метка среди всех машин
        self._pings: dict = {}      # tr_id -> deque[(t, lat, lon, speed, valid)]
        self._version: dict = {}    # tr_id -> сколько отметок принято (сброс кэша прогноза)
        self._cache: dict = {}      # tr_id -> {"version", "at", "forecast"}
        self._lock = threading.Lock()

    @property
    def units(self) -> set:
        """unit_id из таблицы, для которых есть расписание."""
        return set(self._table)

    def ingest(self, fix) -> bool:
        """Принять отметку (ndtp_protocol.Fix).

        False — машина еще не привязана к рейсу (ее трек копится для map matching) или повтор/опоздавший
        пакет."""
        t = int(fix.gps_time) + self._tz
        # У отметки без фиксации скорость терминала ничего не значит (в выгрузке организаторов она у таких
        # строк почти всегда пуста), а NDTP пустой скорости не передает — считаем ее неизвестной, как в обучении.
        row = (t, float(fix.lat), float(fix.lon), float(fix.speed) if fix.location_valid else float("nan"),
               bool(fix.location_valid))
        with self._lock:
            self._stream_t = t if self._stream_t is None else max(self._stream_t, t)
            tr = self._unit_to_tr.get(fix.unit_id)
            if tr is None:
                _append(self._unknown.setdefault(fix.unit_id, deque()), row)
                return False
            if self._tr_to_unit.get(tr) != fix.unit_id:
                self._release(self._tr_to_unit[tr])    # рейс занят машиной, найденной по треку: таблица главнее
                self._tr_to_unit[tr] = fix.unit_id
            if not _append(self._pings.setdefault(tr, deque()), row):
                return False
            self._version[tr] = self._version.get(tr, 0) + 1
        return True

    def _release(self, unit) -> None:
        """Снять привязку, найденную по треку: машина снова незнакомая, ее рейс свободен."""
        tr = self._unit_to_tr.pop(unit)
        self._by_track.discard(unit)
        self._pings.pop(tr, None)
        self._cache.pop(tr, None)
        self._version[tr] = self._version.get(tr, 0) + 1
        self._unknown[unit] = deque()

    def _match_unknown(self, T: int) -> None:
        """Сопоставить незнакомые машины с рейсами по треку; привязка — после CONFIRM совпадений подряд."""
        with self._lock:
            due = [u for u in self._unknown if self._next_try.get(u, -1) <= T][:MAX_MATCH]
            busy = set(self._pings)                    # у этих рейсов уже есть своя машина в потоке
            tracks = {u: np.array(self._unknown[u], dtype=float) for u in due}
        for u, arr in tracks.items():
            self._next_try[u] = T + MATCH_EVERY_S
            found = None
            if len(arr):
                found = match(arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 4] > 0, self._index, exclude=busy)
            tr = found["tr_id"] if found else None
            prev, n = self._streak.get(u, (None, 0))
            self._streak[u] = (tr, n + 1 if tr is not None and tr == prev else int(tr is not None))
            if tr is None or self._streak[u][1] < CONFIRM:
                continue
            with self._lock:
                if tr in self._pings or u not in self._unknown:
                    continue
                self._unit_to_tr[u], self._tr_to_unit[tr] = tr, u
                self._by_track.add(u)
                self._pings[tr] = self._unknown.pop(u)
                self._version[tr] = self._version.get(tr, 0) + 1
                self._streak.pop(u, None)
            busy.add(tr)

    def forecasts(self, now: int = None) -> dict:
        """unit_id -> прогноз (dict) на момент now (по умолчанию — часы потока).

        Машина пересчитывается, только если от нее пришли новые отметки и с прошлого расчета прошло не
        меньше min_interval_s; за один вызов пересчитывается не больше max_recompute машин (самые
        «залежавшиеся»), остальные берутся из кэша: дашборд опрашивает сервис каждые пару секунд."""
        with self._lock:
            T = self._stream_t if now is None else int(now)
        if T is None:
            return {}
        self._match_unknown(T)
        with self._lock:
            trs = list(self._pings)
        clock, out, todo = self._clock(), {}, []
        for tr in trs:
            cached, version = self._cache.get(tr), self._version[tr]
            if cached is None or (cached["version"] != version and clock - cached["at"] >= self._min_interval):
                todo.append((cached["at"] if cached else -1.0, tr))
        for _, tr in sorted(todo)[:self._max_recompute]:
            with self._lock:
                rows, version = list(self._pings[tr]), self._version[tr]
            self._cache[tr] = {"version": version, "at": clock, "forecast": self._forecast(tr, rows, T)}
        for tr in trs:
            if tr in self._cache:
                fc = self._cache[tr]["forecast"]
                out[self._tr_to_unit[tr]] = fc if T - fc["last_ping"] <= STALE_S else {**fc, "status": "no_signal"}
        return out

    def _forecast(self, tr: str, rows: list, T: int) -> dict:
        arr = np.array(rows, dtype=float)
        arr = arr[arr[:, 0] <= T]                              # будущего для момента T нет
        unit = self._tr_to_unit[tr]
        matched_by = "track" if unit in self._by_track else "table"
        if len(arr) == 0:
            return {"unit_id": unit, "tr_id": tr, "T": T, "speed": 0.0, "last_ping": T - STALE_S * 2,
                    "matched_by": matched_by, "status": "no_signal"}
        known = arr[np.isfinite(arr[:, 3]), 3]              # скорость невалидной отметки неизвестна (NaN)
        base = {"unit_id": unit, "tr_id": tr, "T": T, "speed": float(known[-1]) if len(known) else 0.0,
                "last_ping": int(arr[-1, 0]), "matched_by": matched_by}
        if arr[:, 4].sum() < MIN_VALID_PINGS:
            return {**base, "status": "few_pings"}
        plan = self._plan_by_tr[tr]
        ahead = plan[(plan["t_plan"] > T + HORIZON_S[0]) & (plan["t_plan"] <= T + HORIZON_S[1])]
        if ahead.empty:
            return {**base, "status": "no_target"}          # рейс заканчивается или перерыв в расписании
        target = ahead.iloc[0]
        traffic = {tr: {"t": arr[:, 0].astype("int64"), "lat": arr[:, 1], "lon": arr[:, 2],
                        "speed": arr[:, 3], "valid": arr[:, 4] > 0}}
        pts = pd.DataFrame({"tr_id": [tr], "T_s": [T], "tgt_s": [int(target["t_plan"])],
                            "target_stop_id": [target["tt_action_item_id"]]})
        det = estimate_cur_dev_detail(pts, traffic, plan)
        pts["cur_dev_s"] = det["cur_dev_est"].to_numpy()
        X = full_features(pts, traffic, plan).reindex(columns=self._features)
        delay = float(self._reg.predict(X)[0])
        probs = predict_class_probs(X, self._clf).iloc[0]
        cur = float(det["cur_dev_est"].iloc[0])
        return {**base, "status": "ok",
                "target_stop_id": target["tt_action_item_id"],
                "target_stop": self._names.get(target["tt_action_item_id"], ""),
                "target_plan": int(target["t_plan"]),
                "delay_s": delay,
                "cur_dev_s": None if np.isnan(cur) else cur,
                "cur_dev_source": det["source"].iloc[0] or None,
                "p_early": float(probs["early"]), "p_ontime": float(probs["ontime"]), "p_late": float(probs["late"]),
                "reasons": explain(X, top_k=3, model=self._reg)[0]}


def _append(buf: deque, row: tuple) -> bool:
    """Добавить отметку в буфер машины, отбросив повтор или опоздавший пакет и историю старше HISTORY_S."""
    if buf and row[0] <= buf[-1][0]:
        return False
    buf.append(row)
    while buf[0][0] < row[0] - HISTORY_S:
        buf.popleft()
    return True


def load_forecaster(tz_offset_s: int = 0, **kw) -> LiveForecaster:
    """Собрать прогнозист из файлов. FileNotFoundError, если онлайн-модели еще не обучены."""
    for path in (ONLINE_REGRESSOR_PATH, ONLINE_CLASSIFIER_PATH):
        if not path.exists():
            raise FileNotFoundError(f"нет {path.name}: запустите python scripts/model_online.py")
    plan, names, unit_to_tr = load_assets()
    reg = CatBoostRegressor().load_model(str(ONLINE_REGRESSOR_PATH))
    return LiveForecaster(plan, unit_to_tr, names, reg, load_classifier(ONLINE_CLASSIFIER_PATH),
                          tz_offset_s=tz_offset_s, **kw)
