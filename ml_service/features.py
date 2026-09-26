"""Признаки из телеметрии на момент T.

Правило честности: для точки T используется только телеметрия с event_time <= T и
плановое расписание. Факт из schedule.csv (time_fact_begin) не используется никогда —
его нет в validate, и модель на нем развалилась бы на сдаче.

Это единственное место, где считаются признаки: обучение, сдача и сервис берут их отсюда.
"""
from pathlib import Path

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

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "hackathon"
MODELS = ROOT / "models"
CLASSES = ("early", "ontime", "late")
EARLY_S, LATE_S = -60, 120          # порог классов: задержка < -60 с — early, > +120 с — late


def delay_class(delay_s):
    """Класс по задержке в секундах (правило организаторов)."""
    d = np.asarray(delay_s, float)
    return np.where(d < EARLY_S, "early", np.where(d > LATE_S, "late", "ontime"))


def load_points(path) -> pd.DataFrame:
    """labels_*.csv или points.csv: добавляет T_s и tgt_s (секунды от эпохи)."""
    df = pd.read_csv(path, dtype={"sample_id": str, "tr_id": str, "target_stop_id": str})
    df["T_s"] = to_ts(df["T"])
    df["tgt_s"] = to_ts(df["target_time_begin"])
    return df


def base_features(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    X["cur_dev_s"] = df["cur_dev_s"]
    X["horizon_s"] = df["tgt_s"] - df["T_s"]
    X["tgt_min_of_day"] = (df["tgt_s"] % 86400) / 60
    return X


def full_features(points: pd.DataFrame, traffic: dict, plan: pd.DataFrame) -> pd.DataFrame:
    """24 признака v2: базовые + телеметрия. Столбец cur_dev_s берется из points."""
    return pd.concat([base_features(points), build(points, traffic, plan)], axis=1)


def feature_names(name: str = "hackathon_v2_features.csv") -> list:
    """Порядок столбцов, на котором учили модель (сохраняется рядом с ней)."""
    return pd.read_csv(MODELS / name).iloc[:, 0].tolist()


CITY_WINDOW_S = 600


def city_features(points: pd.DataFrame, traffic: dict, window: int = CITY_WINDOW_S) -> pd.DataFrame:
    """«Обстановка в городе» на момент T: средняя скорость и доля простоя всех ТС за последние window секунд.

    Берутся все ТС из traffic (в том числе без разметки), только пинги с event_time <= T.
    Заменяет tgt_min_of_day: не зависит от времени суток, поэтому переносится на другие дни."""
    t = np.concatenate([v["t"] for v in traffic.values()])
    sp = np.concatenate([v["speed"] for v in traffic.values()])
    order = np.argsort(t, kind="stable")
    t, sp = t[order], sp[order]
    fin = np.isfinite(sp)
    csum = np.concatenate([[0.0], np.cumsum(np.where(fin, sp, 0.0))])
    cstop = np.concatenate([[0.0], np.cumsum(np.where(fin, sp < STOPPED_KMH, 0.0))])
    cnt = np.concatenate([[0], np.cumsum(fin)])
    T = points["T_s"].to_numpy()
    hi = np.searchsorted(t, T, side="right")                 # event_time <= T
    lo = np.searchsorted(t, T - window, side="right")        # event_time > T - window
    n = (cnt[hi] - cnt[lo]).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        speed = np.where(n > 0, (csum[hi] - csum[lo]) / n, np.nan)
        stopped = np.where(n > 0, (cstop[hi] - cstop[lo]) / n, np.nan)
    return pd.DataFrame({f"city_speed_mean_{window}": speed, f"city_stopped_share_{window}": stopped},
                        index=points.index)
