"""Прогноз задержек по живому потоку отметок (NDTP) на моделях хакатона.

Поток NDTP отдает только «машина X в момент t была в точке (lat, lon)». Для прогноза нужны:
  * сопоставление unit_id -> tr_id (в данных хакатона это взаимно однозначные столбцы traffic.csv);
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
from .models import ONLINE_CLASSIFIER_PATH, ONLINE_REGRESSOR_PATH, load_classifier, predict_class_probs
from .reasons import explain

HORIZON_S = (600, 900)     # целевая остановка: плановое прибытие в (T+10 мин, T+15 мин]
HISTORY_S = 3600           # сколько истории отметок держим: хватает и признакам (10 мин), и cur_dev
MIN_VALID_PINGS = 2
STALE_S = 300              # машина молчит дольше (по часам потока) — прогноз не выдаем
MAX_RECOMPUTE = 8          # сколько машин пересчитать за один запрос: остальные отдаются из кэша

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
        self._unit_to_tr = {u: tr for u, tr in unit_to_tr.items() if tr in self._plan_by_tr}
        self._tr_to_unit = {tr: u for u, tr in self._unit_to_tr.items()}
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
        """unit_id, для которых есть расписание и, значит, возможен прогноз."""
        return set(self._unit_to_tr)

    def ingest(self, fix) -> bool:
        """Принять отметку (ndtp_protocol.Fix). False — машина без расписания или повтор/опоздавший пакет."""
        tr = self._unit_to_tr.get(fix.unit_id)
        if tr is None:
            return False
        t = int(fix.gps_time) + self._tz
        with self._lock:
            buf = self._pings.setdefault(tr, deque())
            if buf and t <= buf[-1][0]:
                return False
            # У отметки без фиксации скорость терминала ничего не значит (в выгрузке организаторов она у таких
            # строк почти всегда пуста), а NDTP пустой скорости не передает — считаем ее неизвестной, как в обучении.
            speed = float(fix.speed) if fix.location_valid else float("nan")
            buf.append((t, float(fix.lat), float(fix.lon), speed, bool(fix.location_valid)))
            while buf[0][0] < t - HISTORY_S:
                buf.popleft()
            self._version[tr] = self._version.get(tr, 0) + 1
            self._stream_t = t if self._stream_t is None else max(self._stream_t, t)
        return True

    def forecasts(self, now: int = None) -> dict:
        """unit_id -> прогноз (dict) на момент now (по умолчанию — часы потока).

        Машина пересчитывается, только если от нее пришли новые отметки и с прошлого расчета прошло не
        меньше min_interval_s; за один вызов пересчитывается не больше max_recompute машин (самые
        «залежавшиеся»), остальные берутся из кэша: дашборд опрашивает сервис каждые пару секунд."""
        with self._lock:
            trs = list(self._pings)
            T = self._stream_t if now is None else int(now)
        if T is None:
            return {}
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
        if len(arr) == 0:
            return {"unit_id": self._tr_to_unit[tr], "tr_id": tr, "T": T, "speed": 0.0, "last_ping": T - STALE_S * 2,
                    "status": "no_signal"}
        known = arr[np.isfinite(arr[:, 3]), 3]              # скорость невалидной отметки неизвестна (NaN)
        base = {"unit_id": self._tr_to_unit[tr], "tr_id": tr, "T": T, "speed": float(known[-1]) if len(known) else 0.0,
                "last_ping": int(arr[-1, 0])}
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


def load_forecaster(tz_offset_s: int = 0, **kw) -> LiveForecaster:
    """Собрать прогнозист из файлов. FileNotFoundError, если онлайн-модели еще не обучены."""
    for path in (ONLINE_REGRESSOR_PATH, ONLINE_CLASSIFIER_PATH):
        if not path.exists():
            raise FileNotFoundError(f"нет {path.name}: запустите python scripts/model_online.py")
    plan, names, unit_to_tr = load_assets()
    reg = CatBoostRegressor().load_model(str(ONLINE_REGRESSOR_PATH))
    return LiveForecaster(plan, unit_to_tr, names, reg, load_classifier(ONLINE_CLASSIFIER_PATH),
                          tz_offset_s=tz_offset_s, **kw)
