"""Признаки из телеметрии на момент T.

Правило честности: для точки T используется только телеметрия с event_time <= T и
плановое расписание. Факт из schedule.csv (time_fact_begin) не используется никогда —
его нет в validate, и модель на нем развалилась бы на сдаче.

Этот же модуль потом переедет в ML-модуль сервиса: признаки в обучении и онлайн
должны считаться одним кодом.
"""
import numpy as np
import pandas as pd

WINDOWS = (120, 300, 600)   # окна истории, секунды
STOPPED_KMH = 3.0
R_EARTH = 6_371_000.0


def to_ts(s: pd.Series) -> pd.Series:
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.99:
        num = num.astype("float64")
        return (num / 1000 if num.median() > 1e11 else num).round().astype("int64")
    dt = pd.to_datetime(s, format="ISO8601", utc=True)
    return ((dt - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).astype("int64")


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(a))


def load_traffic(path) -> dict:
    """tr_id -> массивы телеметрии, отсортированные по времени."""
    df = pd.read_csv(path, usecols=["tr_id", "event_time", "location_valid", "lon", "lat", "speed"],
                     dtype={"tr_id": str})
    df["t"] = to_ts(df["event_time"])
    df["valid"] = df["location_valid"].astype(str).str.lower().eq("true")
    df = df.sort_values(["tr_id", "t"])
    out = {}
    for tr, g in df.groupby("tr_id", sort=False):
        out[tr] = {"t": g["t"].to_numpy(), "lat": g["lat"].to_numpy(float),
                   "lon": g["lon"].to_numpy(float), "speed": g["speed"].to_numpy(float),
                   "valid": g["valid"].to_numpy()}
    return out


def load_plan(path) -> pd.DataFrame:
    """Только плановые колонки расписания. Факт отбрасывается сразу."""
    df = pd.read_csv(path, dtype={"tt_action_item_id": str, "tr_id": str})
    df = df.drop(columns=[c for c in ["time_fact_begin"] if c in df.columns])
    nums = df["geom"].astype(str).str.findall(r"-?\d+\.\d+")
    a = pd.to_numeric(nums.str[0], errors="coerce")
    b = pd.to_numeric(nums.str[1], errors="coerce")
    # Москва: широта ~55, долгота ~37 — большее число это широта
    df["s_lat"], df["s_lon"] = np.maximum(a, b), np.minimum(a, b)
    df["t_plan"] = to_ts(df["time_begin"])
    return df[["tt_action_item_id", "tr_id", "t_plan", "s_lat", "s_lon"]].sort_values(["tr_id", "t_plan"])


def build(points: pd.DataFrame, traffic: dict, plan: pd.DataFrame) -> pd.DataFrame:
    """points: sample_id, tr_id, T_s, tgt_s, target_stop_id. Возвращает признаки по строкам points."""
    stop_xy = plan.set_index("tt_action_item_id")[["s_lat", "s_lon"]]
    plan_by_tr = {tr: g for tr, g in plan.groupby("tr_id", sort=False)}
    rows = []
    for p in points.itertuples(index=False):
        f = {}
        T, tgt = int(p.T_s), int(p.tgt_s)
        tr = traffic.get(p.tr_id)
        if tr is not None:
            k = np.searchsorted(tr["t"], T, side="right")        # только event_time <= T
            t, v, sp = tr["t"][:k], tr["valid"][:k], tr["speed"][:k]
            lat, lon = tr["lat"][:k], tr["lon"][:k]
            if k:
                f["last_ping_age_s"] = T - t[-1]
                f["speed_last"] = sp[-1]
            for w in WINDOWS:
                m = t > T - w
                f[f"speed_mean_{w}"] = sp[m].mean() if m.any() else np.nan
                f[f"stopped_share_{w}"] = (sp[m] < STOPPED_KMH).mean() if m.any() else np.nan
                mv = m & v
                if mv.sum() >= 2:
                    path = haversine(lat[mv][:-1], lon[mv][:-1], lat[mv][1:], lon[mv][1:]).sum()
                    f[f"path_m_{w}"] = path
                    f[f"eff_speed_{w}"] = path / w                # м/с с учетом стоянок
            if v.any():
                j = np.flatnonzero(v)[-1]
                f["pos_age_s"] = T - t[j]
                cur_lat, cur_lon = lat[j], lon[j]
            else:
                cur_lat = cur_lon = np.nan
        else:
            cur_lat = cur_lon = np.nan

        if p.target_stop_id in stop_xy.index:
            s = stop_xy.loc[p.target_stop_id]
            s = s.iloc[0] if isinstance(s, pd.DataFrame) else s
            f["dist_straight_m"] = haversine(cur_lat, cur_lon, s["s_lat"], s["s_lon"])

        g = plan_by_tr.get(p.tr_id)
        if g is not None:
            ahead = g[(g["t_plan"] > T) & (g["t_plan"] <= tgt)]
            f["n_stops_ahead"] = len(ahead)
            if len(ahead) and not np.isnan(cur_lat):
                la, lo = ahead["s_lat"].to_numpy(), ahead["s_lon"].to_numpy()
                route = haversine(cur_lat, cur_lon, la[0], lo[0])
                if len(ahead) > 1:
                    route += haversine(la[:-1], lo[:-1], la[1:], lo[1:]).sum()
                f["dist_route_m"] = route
                f["req_speed"] = route / max(tgt - T, 1)          # с какой скоростью надо ехать
                for w in (300, 600):
                    es = f.get(f"eff_speed_{w}")
                    if es is not None:
                        eta = route / max(es, 0.5)
                        f[f"phys_delay_{w}"] = float(np.clip(T + eta - tgt, -1800, 1800))
        rows.append(f)
    return pd.DataFrame(rows, index=points.index)