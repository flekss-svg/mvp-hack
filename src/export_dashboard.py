"""Прогон тестового дня через поток и модель -> компактный JSON для дашборда -> HTML.

Дашборд сам восстанавливает положение машин на любой момент дня (интерполяция между
остановками), поэтому храним не кадры, а события рейсов.
"""
import glob
import json
import pickle
import sys

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from config import PROC, MODELS, REPORTS, DASH, LATE_THRESHOLD_MIN
from features import FEATURES, StreamState, load_schedule_index, run_day
from train import day_context


def main(date=None):
    files = sorted(glob.glob(str(PROC / "fact" / "day=*.parquet")))
    test = files[21:]
    f = next((x for x in test if date and date in x), test[3])
    date = f.split("day=")[1][:10]
    meta = pd.read_parquet(PROC / "sim_meta.parquet").set_index("date")

    model = CatBoostClassifier()
    model.load_model(str(MODELS / "delay_catboost.cbm"))
    with open(MODELS / "hist_profile.pkl", "rb") as fh:
        hist = pickle.load(fh)
    routes = pd.read_parquet(PROC / "routes.parquet")
    stops = pd.read_parquet(PROC / "stops.parquet")
    schedule = load_schedule_index()

    state = StreamState(schedule, hist, dict(zip(routes.route_id, routes["mode"])))
    state.set_context(**day_context(date, meta.loc[date]))
    df = pd.read_parquet(f)
    X, M = run_day(state, df, sample=1.0)
    M["risk"] = model.predict_proba(X[FEATURES])[:, 1]
    print(f"{date}: {len(df):,} событий, {len(M):,} прогнозов")

    # проверка уровней риска на этом дне
    lv = np.digitize(M.risk, [0.3, 0.6])
    for i, n in enumerate(["низкий", "средний", "высокий"]):
        m = lv == i
        print(f"  риск {n:8s}: {m.mean():6.1%} прогнозов, опоздали через 12 мин: {M.y[m].mean():.1%}")

    risk = dict(zip(zip(M.trip_id, M.k), M.risk))

    # --- компактная упаковка ---
    used = sorted(set(df.stop_id))
    sidx = {s: i for i, s in enumerate(used)}
    sxy = stops.set_index("stop_id").loc[used]
    stops_out = [[round(x, 5), round(y, 5)] for x, y in zip(sxy.stop_lon, sxy.stop_lat)]
    stop_names = list(sxy.stop_name)
    ridx = {r: i for i, r in enumerate(routes.route_id)}
    routes_out = [[a, b, c] for a, b, c in zip(routes.route_short_name, routes.route_long_name,
                                               routes["mode"])]
    pat_idx, patterns, trips_out = {}, [], []
    for tid, g in df.sort_values(["trip_id", "k"]).groupby("trip_id", sort=False):
        pat = tuple(sidx[s] for s in g.stop_id)
        if pat not in pat_idx:
            pat_idx[pat] = len(patterns)
            patterns.append(list(pat))
        plan = g.plan.to_numpy()
        fact_s = np.round(g.fact.to_numpy() * 60).astype(int)
        rk = [int(round(risk[(tid, k)] * 100)) if (tid, k) in risk else -1 for k in g.k]
        trips_out.append([ridx[g.route_id.iloc[0]], int(g.direction_id.iloc[0]),
                          pat_idx[pat], int(plan[0]), np.diff(plan).astype(int).tolist(),
                          int(fact_s[0]), np.diff(fact_s).tolist(), rk])

    metrics = json.load(open(REPORTS / "metrics.json"))
    m = meta.loc[date]
    data = dict(date=date, dow=pd.Timestamp(date).dayofweek,
                rain=dict(level=float(m.rain), start=float(m.rain_from), end=float(m.rain_to)),
                threshold=LATE_THRESHOLD_MIN, stops=stops_out, stopNames=stop_names,
                routes=routes_out, patterns=patterns, trips=trips_out, metrics=metrics)
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (DASH / "data.json").write_text(js, encoding="utf-8")
    html = (DASH / "template.html").read_text(encoding="utf-8").replace("__DATA__", js)
    (DASH / "dashboard.html").write_text(html, encoding="utf-8")
    print(f"dashboard.html: {len(html) / 1e6:.1f} МБ, рейсов {len(trips_out):,}, "
          f"шаблонов остановок {len(patterns):,}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
