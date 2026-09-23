"""Прогон тестового дня через движок признаков и модель -> data.json для дашборда.

Дашборд (dashboard/index.html) — статичный HTML-файл, который сам грузит data.json через
fetch() и восстанавливает положение машин на любой момент дня (интерполяция между
остановками), поэтому храним не кадры, а события рейсов. Файл dashboard/index.html
перегенерировать не нужно — меняется только data.json.

Для «живого» режима дашборд вместо data.json опрашивает GET /risk работающего сервиса
(см. app/api.py) — это переключается прямо в интерфейсе дашборда.
"""
import json
import sys

import numpy as np
import pandas as pd

from app.config import DASH, LATE_THRESHOLD_MIN, REPORTS
from app.data_sources import processed_repository as repo
from app.engine.stream_state import StreamState, run_day
from app.model.artifacts import ModelArtifacts
from app.model.training import day_context


def main(date: str | None = None) -> None:
    files = repo.list_fact_days()
    test = files[21:]
    f = next((x for x in test if date and date in str(x)), test[3])
    date = repo.fact_day_date(f)
    meta = repo.read_sim_meta()

    artifacts = ModelArtifacts.load()
    routes = repo.read_routes()
    stops = repo.read_stops()

    state = StreamState(artifacts.schedule, artifacts.hist_profile, artifacts.route_mode)
    state.set_context(**day_context(date, meta.loc[date]))
    df = repo.read_fact_day(f)
    X, M = run_day(state, df, sample=1.0)
    M["risk"] = artifacts.predictor.predict_risk(X)
    print(f"{date}: {len(df):,} событий, {len(M):,} прогнозов")

    # проверка уровней риска на этом дне
    lv = np.digitize(M.risk, [0.3, 0.6])
    for i, n in enumerate(["низкий", "средний", "высокий"]):
        m = lv == i
        print(f"  риск {n:8s}: {m.mean():6.1%} прогнозов, опоздали через 12 мин: {M.y[m].mean():.1%}")

    risk_by_key = dict(zip(zip(M.trip_id, M.k), M.risk))

    # --- компактная упаковка для фронтенда ---
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
        rk = [int(round(risk_by_key[(tid, k)] * 100)) if (tid, k) in risk_by_key else -1 for k in g.k]
        trips_out.append([ridx[g.route_id.iloc[0]], int(g.direction_id.iloc[0]),
                          pat_idx[pat], int(plan[0]), np.diff(plan).astype(int).tolist(),
                          int(fact_s[0]), np.diff(fact_s).tolist(), rk])

    metrics = json.loads((REPORTS / "metrics.json").read_text(encoding="utf-8"))
    m = meta.loc[date]
    data = dict(date=date, dow=pd.Timestamp(date).dayofweek,
                rain=dict(level=float(m.rain), start=float(m.rain_from), end=float(m.rain_to)),
                threshold=LATE_THRESHOLD_MIN, stops=stops_out, stopNames=stop_names,
                routes=routes_out, patterns=patterns, trips=trips_out, metrics=metrics)
    DASH.mkdir(parents=True, exist_ok=True)
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (DASH / "data.json").write_text(js, encoding="utf-8")
    print(f"data.json: {len(js) / 1e6:.1f} МБ, рейсов {len(trips_out):,}, "
          f"шаблонов остановок {len(patterns):,}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
