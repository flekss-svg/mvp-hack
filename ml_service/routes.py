"""Номер маршрута для машины хакатона по ее расписанию.

В данных организаторов номера маршрута нет — только tr_id машины и точки ее расписания. Но точки
расписания стоят на реальных остановках, а справочник data.mos.ru (app/data_sources/mos_ru_routes.py)
знает, какие маршруты обслуживают каждую остановку. Маршрут машины — тот, чьи остановки покрывают
почти все точки ее расписания. На данных хакатона лучший маршрут покрывает 97–100% точек, следующий —
не больше ~70%; где разрыв меньше, номер не ставим: лучше «не определен», чем чужой маршрут.
"""
from collections import Counter

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .features import ROOT

ROUTE_STOPS = ROOT / "data" / "processed" / "route_stops.parquet"
NEAR_M = 60          # точка расписания «на остановке», если до нее не дальше
MIN_SHARE = 0.8      # маршрут должен покрывать хотя бы такую долю точек у остановок
MIN_MARGIN = 0.15    # и опережать второй по покрытию хотя бы на столько

_KX, _KY = np.cos(np.radians(55.75)) * 111_320, 110_540   # градусы -> метры для Москвы


def load_route_stops(path=ROUTE_STOPS) -> pd.DataFrame | None:
    """Справочник из репозитория. Нет файла — номера маршрутов просто не показываются."""
    return pd.read_parquet(path) if path.exists() else None


def match_routes(plan: pd.DataFrame, route_stops: pd.DataFrame | None) -> dict:
    """plan: tr_id, s_lat, s_lon. -> tr_id -> {route, route_name, mode} для уверенно опознанных."""
    if route_stops is None or route_stops.empty or plan.empty:
        return {}
    stops = route_stops.drop_duplicates("stop_id").reset_index(drop=True)
    tree = cKDTree(np.c_[stops.stop_lon * _KX, stops.stop_lat * _KY])
    routes_of = route_stops.groupby("stop_id")["route_id"].agg(set)
    info = route_stops.drop_duplicates("route_id").set_index("route_id")

    dist, idx = tree.query(np.c_[plan.s_lon.to_numpy() * _KX, plan.s_lat.to_numpy() * _KY])
    near_stop = pd.Series(np.where(dist <= NEAR_M, stops.stop_id.to_numpy()[idx], None), index=plan.index)
    out = {}
    for tr, stop_ids in near_stop.groupby(plan.tr_id.to_numpy()):
        on_stop = stop_ids.dropna()
        if on_stop.empty:
            continue
        votes = Counter(r for s in on_stop for r in routes_of[s])
        (best, n), *rest = votes.most_common(2)
        second = rest[0][1] if rest else 0
        if n / len(on_stop) >= MIN_SHARE and (n - second) / len(on_stop) >= MIN_MARGIN:
            row = info.loc[best]
            out[tr] = {"route": row.route_short_name, "route_name": row.route_long_name, "mode": row["mode"]}
    return out
