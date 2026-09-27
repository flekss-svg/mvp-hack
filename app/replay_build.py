"""Прогон записанного дня через движок признаков и модель -> серверный кэш для API.

Результат остается на сервере: app/service/replay_service.py поднимает этот кэш и отдает
фронтенду уже готовые кадры (GET /api/replay/frame), фронтенд ничего не пересчитывает.

Запуск:
    python -m app.replay_build [YYYY-MM-DD]
"""
import pickle
import sys

import numpy as np
import pandas as pd

from app.config import LATE_THRESHOLD_MIN, REPLAY_CACHE, RISK_LEVELS
from app.data_sources import processed_repository as repo
from app.engine.stream_state import StreamState, run_day
from app.model.artifacts import ModelArtifacts
from app.model.explain import REASONS, TOP, main_reasons, reason_text
from app.model.training import day_context
from app.service.replay_service import KEY_SPAN, ReplayDay


def _pick_day(date: str | None):
    files = repo.list_fact_days()
    test = files[21:]
    if not test:
        raise FileNotFoundError(
            "Нет фактических дней в data/processed/fact. Сначала расписание и факт движения: "
            "python3 -m app.data_sources.mos_ru_schedule, затем python3 -m app.simulation.synthetic_telemetry")
    return next((x for x in test if date and date in str(x)), test[min(3, len(test) - 1)])

def build(date: str | None = None) -> ReplayDay:
    path = _pick_day(date)
    date = repo.fact_day_date(path)
    meta = repo.read_sim_meta()
    artifacts = ModelArtifacts.load()
    routes = repo.read_routes()
    stops = repo.read_stops()

    state = StreamState(artifacts.schedule, artifacts.hist_profile, artifacts.route_mode)
    state.set_context(**day_context(date, meta.loc[date]))
    df = repo.read_fact_day(path)
    X, M = run_day(state, df, sample=1.0)
    M["risk"] = artifacts.predictor.predict_risk(X)
    M["fdelay"] = artifacts.regressor.predict_delay(X)
    # Причину объясняем там, где диспетчеру ее вообще покажут: средний риск и выше.
    # SHAP заметно дороже самого прогноза, считать его на весь день незачем.
    reason = np.full((len(M), TOP), -1, np.int16)
    explain_rows = np.flatnonzero(M.risk.to_numpy() >= RISK_LEVELS[0])
    if len(explain_rows):
        reason[explain_rows] = main_reasons(artifacts.predictor.explain(X.iloc[explain_rows]))
    print(f"{date}: {len(df):,} событий, {len(M):,} прогнозов, объяснено {len(explain_rows):,}")
    texts = pd.Series([reason_text(r) or "(причина не выявлена)" for r in reason[explain_rows]])
    for text, n in texts.value_counts().head(8).items():
        print(f"  {n:7,}  {text}")
    
    lv = np.digitize(M.risk, list(RISK_LEVELS))
    for i, n in enumerate(["низкий", "средний", "высокий"]):
        m = lv == i
        print(f"  риск {n:8s}: {m.mean():6.1%} прогнозов, опоздали через 12 мин: {M.y[m].mean():.1%}")

    df = df.sort_values(["trip_id", "k"], kind="stable").reset_index(drop=True)

    # --- остановки: оставляем только те, что встречаются в этом дне ---
    used = pd.Index(sorted(set(df.stop_id)))
    sxy = stops.set_index("stop_id").reindex(used)
    stop_lon = sxy.stop_lon.to_numpy(np.float32)
    stop_lat = sxy.stop_lat.to_numpy(np.float32)
    stop_names = sxy.stop_name.fillna("").tolist()

    # --- события ---
    trip_code, trip_ids = pd.factorize(df.trip_id)
    ev_trip = trip_code.astype(np.int32)
    ev_stop = used.get_indexer(df.stop_id).astype(np.int32)
    ev_plan = df.plan.to_numpy(np.float64)
    ev_fact = df.fact.to_numpy(np.float64)

    # риск и точка его проверки — по ключу (рейс, номер остановки)
    pos = pd.Series(np.arange(len(df)), index=pd.MultiIndex.from_arrays([df.trip_id, df.k]))
    at = pos.reindex(pd.MultiIndex.from_arrays([M.trip_id, M.k])).to_numpy()
    tgt = pos.reindex(pd.MultiIndex.from_arrays([M.trip_id, M.h])).to_numpy()
    ev_risk = np.full(len(df), -1.0, np.float32)
    ev_risk[at] = M.risk.to_numpy(np.float32)
    ev_target = np.full(len(df), -1, np.int64)
    ev_target[at] = np.where(np.isnan(tgt), -1, np.nan_to_num(tgt)).astype(np.int64)
    ev_fdelay = np.full(len(df), np.nan, np.float32)
    ev_fdelay[at] = M.fdelay.to_numpy(np.float32)
    ev_reason = np.full((len(df), TOP), -1, np.int16)
    ev_reason[at] = reason

    # --- глобальная сортировка по (рейс, время) ---
    key = ev_trip * KEY_SPAN + ev_fact
    order = np.argsort(key, kind="stable")
    inv = np.empty_like(order)
    inv[order] = np.arange(len(order))
    ev_target = np.where(ev_target >= 0, inv[np.maximum(ev_target, 0)], -1)[order]
    ev_trip, ev_stop = ev_trip[order], ev_stop[order]
    ev_plan, ev_fact, ev_risk = ev_plan[order], ev_fact[order], ev_risk[order]
    ev_fdelay, ev_reason = ev_fdelay[order], ev_reason[order]
    ev_key = key[order]

    trip_off = np.concatenate([[0], np.flatnonzero(np.diff(ev_trip)) + 1, [len(ev_trip)]]).astype(np.int64)

    # --- рейсы: маршрут и вид транспорта ---
    first = df.groupby("trip_id", sort=False).first().reindex(trip_ids)
    route_ids = pd.Index(routes.route_id)
    trip_route = route_ids.get_indexer(first.route_id).astype(np.int32)
    modes = ["bus", "tram", "trolley", "other"]
    mode_of_route = routes["mode"].map({m: i for i, m in enumerate(modes)}).fillna(3).to_numpy(np.int32)
    trip_mode = mode_of_route[trip_route]

    # --- перегоны и их прохождения (подсветка медленных участков) ---
    same = ev_trip[:-1] == ev_trip[1:]
    pairs = np.stack([ev_stop[:-1][same], ev_stop[1:][same]], axis=1)
    seg_uniq, seg_inv = np.unique(pairs, axis=0, return_inverse=True)
    excess = ((ev_fact[1:] - ev_fact[:-1]) - (ev_plan[1:] - ev_plan[:-1]))[same]
    trav_t = ev_fact[1:][same]
    o = np.argsort(trav_t, kind="stable")

    m = meta.loc[date]
    day = ReplayDay(
        date=date, dow=int(pd.Timestamp(date).dayofweek),
        rain={"level": float(m.rain), "start": float(m.rain_from), "end": float(m.rain_to)},
        threshold=LATE_THRESHOLD_MIN,
        t_min=float(ev_fact[trip_off[:-1]].min()), t_max=float(ev_fact[trip_off[1:] - 1].max()),
        stop_lon=stop_lon, stop_lat=stop_lat, stop_names=stop_names,
        seg_a=seg_uniq[:, 0].astype(np.int32), seg_b=seg_uniq[:, 1].astype(np.int32),
        ev_stop=ev_stop, ev_plan=ev_plan, ev_fact=ev_fact, ev_risk=ev_risk,
        ev_target=ev_target.astype(np.int64), ev_trip=ev_trip, ev_key=ev_key,
        ev_fdelay=ev_fdelay, ev_reason=ev_reason,
        trip_off=trip_off, trip_route=trip_route, trip_mode=trip_mode,
        route_short=routes.route_short_name.tolist(), route_long=routes.route_long_name.tolist(),
        modes=modes,
        trav_t=trav_t[o], trav_seg=seg_inv[o].astype(np.int32), trav_excess=excess[o].astype(np.float32),
        reasons=REASONS,
    )
    return day


def main(date: str | None = None) -> None:
    day = build(date)
    REPLAY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPLAY_CACHE, "wb") as fh:
        # складываем поля, а не сам объект: кэш не зависит от того, как импортирован модуль
        pickle.dump(vars(day), fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"{REPLAY_CACHE}: {REPLAY_CACHE.stat().st_size / 1e6:.1f} МБ, "
          f"рейсов {len(day.trip_off) - 1:,}, перегонов {len(day.seg_a):,}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
