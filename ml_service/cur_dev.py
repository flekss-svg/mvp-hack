"""Онлайн-оценка cur_dev_s: задержка на последней остановке, плановое время которой уже наступило.

В живом потоке cur_dev_s никто не присылает, поэтому оцениваем его сами.

Что такое cur_dev_s у организаторов (установлено на train по телеметрии и разметке): это
отклонение факта от плана на остановке k0 — последней, у которой плановое время t_plan <= T.
Причем фактическое прибытие в k0 у опаздывающей машины может случиться *после* T (на train
около половины точек). В живом потоке будущего нет, поэтому оценка двухступенчатая:
  1) прибытие в k0 уже видно в пингах до T — берем его: при короткой стоянке момент наибольшего
     сближения, при длинной (терминал, простой) — плановое время, зажатое в интервал стоянки
     (если план попал внутрь стоянки, отклонение ≈ 0, иначе — разница между входом и планом);
  2) иначе прогнозируем прибытие: остаток пути до k0 по остановкам маршрута / средняя скорость
     последних минут, но не раньше T.

Правила честности те же, что у признаков: только пинги с event_time <= T и плановое расписание,
time_fact_begin не используется. Константы подобраны на train (scripts/check_service.py).
"""
import numpy as np
import pandas as pd

from .features import R_EARTH

RADIUS_M = 50.0          # остановка «пройдена», если траектория подошла к ней ближе
RADIUS_WIDE_M = 150.0    # если в RADIUS_M траектория не подходила — ищем прибытие в этом радиусе
DWELL_SHORT_S = 240      # стоянка в радиусе дольше — считаем длинной (терминал, простой)
DEV_MAX_S = 900          # |задержка| больше — считаем, что это другой рейс той же остановки
OFFSET_S = 0.0           # сдвиг оценки по прибытию (наш момент − момент организаторов)
VEL_WINDOW_S = 300       # окно средней скорости для прогноза, с
V_MIN = 1.0              # минимальная скорость в прогнозе, м/с (иначе ETA улетает в бесконечность)
V_DEFAULT = 4.5          # если по пингам скорость не посчитать, м/с (медиана по train)
ETA_SPEED_W = 0.0        # доля прогноза «по скорости» (остаток пути / скорость) против «по расписанию»
ETA_ADD_S = 0.0          # добавка к прогнозу прибытия, с
BACK_STOPS = 15          # сколько остановок назад от k0 смотрим при проекции положения на маршрут
FWD_STOPS = 5            # и вперед (машина могла уже проехать k0, а пинги рядом с ней не попали)
MAX_OFF_ROUTE_M = 300.0  # дальше от ломаной маршрута — положению не доверяем
LAT0 = 55.75             # для локальной проекции (Москва)


def _xy(lat, lon):
    return (np.radians(np.asarray(lon, float)) * np.cos(np.radians(LAT0)) * R_EARTH,
            np.radians(np.asarray(lat, float)) * R_EARTH)


def _prepare_traffic(traffic: dict) -> dict:
    """tr_id -> валидные пинги в метрах (только там, где известна позиция)."""
    out = {}
    for tr, v in traffic.items():
        m = v["valid"] & np.isfinite(v["lat"]) & np.isfinite(v["lon"])
        x, y = _xy(v["lat"][m], v["lon"][m])
        out[tr] = (v["t"][m].astype(float), x, y)
    return out


def _closest_arrival(t, x, y, sx, sy, radius):
    """Момент наибольшего сближения траектории (ломаной по пингам) с остановкой; NaN, если ближе radius не было.

    Время внутри отрезка между соседними пингами интерполируется линейно."""
    dx, dy, dt = x[1:] - x[:-1], y[1:] - y[:-1], t[1:] - t[:-1]
    seg2 = np.maximum(dx * dx + dy * dy, 1e-9)
    px, py = x[:-1] - sx, y[:-1] - sy
    u = np.clip(-(px * dx + py * dy) / seg2, 0.0, 1.0)
    dist = np.hypot(px + u * dx, py + u * dy)
    i = int(np.argmin(dist))
    return t[i] + u[i] * dt[i] if dist[i] <= radius else np.nan


def _arrival(t, x, y, sx, sy, t_plan, T, radius, dwell_short):
    """Момент прибытия на остановку по пингам до T (NaN — траектория не подходила ближе radius)."""
    closest = _closest_arrival(t, x, y, sx, sy, radius)
    if not np.isfinite(closest):
        return np.nan
    inside = np.flatnonzero(np.hypot(x - sx, y - sy) <= radius)
    if len(inside) == 0:
        return closest                                          # проскочила между пингами
    first = t[inside[0]]
    last = T if inside[-1] == len(t) - 1 else t[inside[-1]]     # ещё внутри — стоит до T
    if last - first <= dwell_short:
        return closest
    return min(max(t_plan, first), last)


def _route_position(px, py, tp, sx, sy, k0, back, fwd, max_off):
    """Положение точки (px, py) на маршруте (ломаная по остановкам) относительно остановки k0.

    Возвращает (расстояние до k0 вдоль маршрута, м — отрицательное, если k0 уже проехала;
    плановое время, в которое по расписанию машина была бы в этой точке). (NaN, NaN), если точка
    дальше max_off метров от ломаной."""
    a, b = max(k0 - back, 0), min(k0 + fwd, len(sx) - 1)
    if b <= a:
        return np.nan, np.nan
    ax, ay, bx, by = sx[a:b], sy[a:b], sx[a + 1:b + 1], sy[a + 1:b + 1]
    dx, dy = bx - ax, by - ay
    length = np.hypot(dx, dy)
    u = np.clip(((px - ax) * dx + (py - ay) * dy) / np.maximum(length ** 2, 1e-9), 0.0, 1.0)
    off = np.hypot(ax + u * dx - px, ay + u * dy - py)
    s = int(np.argmin(off))
    if off[s] > max_off:
        return np.nan, np.nan
    pos_along = length[:s].sum() + u[s] * length[s]         # путь от остановки a до точки
    k0_along = length[:k0 - a].sum() if k0 > a else 0.0     # и от a до k0
    return k0_along - pos_along, tp[a + s] + u[s] * (tp[a + s + 1] - tp[a + s])


def _speed(t, x, y, hi, window, default):
    """Эффективная скорость (путь / время, с учётом стоянок) по пингам до индекса hi за последние window с."""
    lo = np.searchsorted(t, t[hi - 1] - window, side="left")
    if hi - lo < 2 or t[hi - 1] - t[lo] < 60:
        return default
    path = np.hypot(np.diff(x[lo:hi]), np.diff(y[lo:hi])).sum()
    return path / (t[hi - 1] - t[lo])


def estimate_cur_dev_detail(points: pd.DataFrame, traffic: dict, plan: pd.DataFrame, *, prepared: dict = None,
                            **over) -> pd.DataFrame:
    """Оценка cur_dev_s по строкам points (нужны tr_id и T_s).

    Столбцы: cur_dev_est (NaN — оценить не удалось) и source: arrival (прибытие видно в пингах),
    eta (k0 ещё впереди: прогноз прибытия), passed (k0 проехана, но в радиус не попала)."""
    P = dict(RADIUS_M=RADIUS_M, RADIUS_WIDE_M=RADIUS_WIDE_M, DWELL_SHORT_S=DWELL_SHORT_S, DEV_MAX_S=DEV_MAX_S, OFFSET_S=OFFSET_S, VEL_WINDOW_S=VEL_WINDOW_S, V_MIN=V_MIN,
             V_DEFAULT=V_DEFAULT, ETA_SPEED_W=ETA_SPEED_W, ETA_ADD_S=ETA_ADD_S, BACK_STOPS=BACK_STOPS,
             FWD_STOPS=FWD_STOPS, MAX_OFF_ROUTE_M=MAX_OFF_ROUTE_M)
    P.update(over)
    tel = prepared if prepared is not None else _prepare_traffic(traffic)
    plan_by_tr = {}
    for tr, g in plan.groupby("tr_id", sort=False):
        sx, sy = _xy(g["s_lat"], g["s_lon"])
        plan_by_tr[tr] = (g["t_plan"].to_numpy(float), sx, sy)

    est = np.full(len(points), np.nan)
    src = np.full(len(points), "", dtype=object)
    for n, p in enumerate(points.itertuples(index=False)):
        if p.tr_id not in tel or p.tr_id not in plan_by_tr:
            continue
        T = float(p.T_s)
        tp, sx, sy = plan_by_tr[p.tr_id]
        k0 = int(np.searchsorted(tp, T, side="right")) - 1     # последняя остановка с t_plan <= T
        t, x, y = tel[p.tr_id]
        hi = int(np.searchsorted(t, T, side="right"))           # только event_time <= T
        if k0 < 0 or hi < 1:
            continue
        lo = int(np.searchsorted(t, tp[k0] - P["DEV_MAX_S"], side="left"))
        if hi - lo >= 2:
            arr = _arrival(t[lo:hi], x[lo:hi], y[lo:hi], sx[k0], sy[k0], tp[k0], T, P["RADIUS_M"],
                           P["DWELL_SHORT_S"])
            if not np.isfinite(arr):
                arr = _closest_arrival(t[lo:hi], x[lo:hi], y[lo:hi], sx[k0], sy[k0], P["RADIUS_WIDE_M"])
            if np.isfinite(arr) and abs(arr - tp[k0]) <= P["DEV_MAX_S"]:
                est[n], src[n] = arr - tp[k0] + P["OFFSET_S"], "arrival"
                continue
        rem, plan_here = _route_position(x[hi - 1], y[hi - 1], tp, sx, sy, k0, P["BACK_STOPS"], P["FWD_STOPS"],
                                         P["MAX_OFF_ROUTE_M"])
        if not np.isfinite(rem):
            continue
        v = max(_speed(t, x, y, hi, P["VEL_WINDOW_S"], P["V_DEFAULT"]), P["V_MIN"])
        w = P["ETA_SPEED_W"]
        travel = w * rem / v + (1 - w) * (tp[k0] - plan_here)   # по скорости / по расписанию
        eta = t[hi - 1] + travel + P["ETA_ADD_S"]
        if rem >= 0:
            eta = max(eta, T)                                   # прибытия до T в пингах не было
        dev = eta - tp[k0]
        if abs(dev) <= P["DEV_MAX_S"] * 2:
            est[n], src[n] = dev, "eta" if rem >= 0 else "passed"
    return pd.DataFrame({"cur_dev_est": est, "source": src}, index=points.index)


def estimate_cur_dev(points: pd.DataFrame, traffic: dict, plan: pd.DataFrame, **kw) -> pd.Series:
    """cur_dev_s по строкам points. NaN — оценить не удалось."""
    return estimate_cur_dev_detail(points, traffic, plan, **kw)["cur_dev_est"]
