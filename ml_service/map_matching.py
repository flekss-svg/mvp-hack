"""Map matching: к какому рейсу относится машина, если ее unit_id неизвестен.

В пакете NDTP нет номера рейса, только unitId терминала. Если терминала нет в таблице unit_id -> tr_id,
рейс определяется по треку: последние отметки машины сравниваются с плановой ниткой каждого рейса —
цепочкой остановок и плановых времен.

Для каждого рейса-кандидата отметки проецируются на ломаную его остановок (окно плана вокруг времени
отметок с запасом на опоздание). По проекции получаются:
  * удаление от маршрута — медиана расстояний отметок до ломаной, м;
  * отклонение от графика — факт минус плановое время в точке проекции, с (медиана);
  * разброс этого отклонения — у «своего» рейса оно почти постоянно, у чужого рейса того же маршрута
    (другая машина по другому графику) или обратного направления — плывет.
Координаты сами по себе рейс не определяют: по одним остановкам ходят до шести машин. Различает время.

Рейс выбирается, если он ближе всех по суммарной оценке, проходит пороги и заметно лучше второго
кандидата. Иначе — None: машина остается без прогноза, это безопаснее ложной привязки.
Пороги подобраны на train (scripts/check_map_matching.py).
"""
import numpy as np
import pandas as pd

from .cur_dev import _xy

WINDOW_S = 600           # сколько последних секунд трека используем
MIN_FIXES = 8            # минимум достоверных отметок в окне
MIN_PATH_M = 300         # минимум пройденного пути: по стоящей машине рейс не определить
DEV_MAX_S = 600          # допустимое отклонение от графика, с
MAX_DIST_M = 80          # медиана удаления отметок от ломаной маршрута
MAX_SPREAD_S = 180       # разброс отклонения от графика по отметкам (межквартильный размах)
DEV_WEIGHT = 0.05        # оценка кандидата, м: удаление + DEV_WEIGHT * |отклонение| + SPREAD_WEIGHT * разброс
SPREAD_WEIGHT = 0.25
MARGIN = 10              # на сколько лучший кандидат должен быть лучше второго
TIME_WEIGHT = 0.1        # м/с: при выборе отрезка проекции минута расхождения с планом = 6 м
PLAN_SLACK_S = 1200      # окно плана вокруг времени отметок: запас на опоздание и опережение
CONFIRM = 2              # привязка — после стольких совпадений подряд (прогноз по потоку)


class TripIndex:
    """Плановые нитки рейсов в метрах: tr_id -> (t_plan, x, y)."""

    def __init__(self, plan: pd.DataFrame):
        self.trips = {}
        for tr, g in plan.sort_values(["tr_id", "t_plan"]).groupby("tr_id", sort=False):
            x, y = _xy(g["s_lat"].to_numpy(float), g["s_lon"].to_numpy(float))
            self.trips[tr] = (g["t_plan"].to_numpy(float), x, y)


def _project(t, px, py, sx, sy, tp):
    """Проекция отметок на ломаную рейса: (расстояние до ломаной, плановое время в точке проекции).

    Маршрут «туда» и «обратно» проходит по одним и тем же местам, поэтому отрезок выбирается не только
    по расстоянию, но и по времени: сначала — ближайший к плану, затем — к плану со сдвигом на
    найденное отклонение машины от графика."""
    ax, ay, dx, dy = sx[:-1], sy[:-1], np.diff(sx), np.diff(sy)
    seg2 = np.maximum(dx * dx + dy * dy, 1e-9)
    u = np.clip(((px[:, None] - ax) * dx + (py[:, None] - ay) * dy) / seg2, 0.0, 1.0)
    dist = np.hypot(ax + u * dx - px[:, None], ay + u * dy - py[:, None])
    plan_t = tp[:-1] + u * np.diff(tp)
    rows, shift = np.arange(len(px)), 0.0
    for _ in range(2):
        k = (dist + TIME_WEIGHT * np.abs(t[:, None] - plan_t - shift)).argmin(axis=1)
        shift = float(np.median(t - plan_t[rows, k]))
    return dist[rows, k], plan_t[rows, k]


def candidates(t, x, y, index: TripIndex, exclude=()) -> list:
    """Оценки всех рейсов для отметок (t, x, y) в метрах; по возрастанию score (лучший первый)."""
    out = []
    for tr, (tp, sx, sy) in index.trips.items():
        if tr in exclude:
            continue
        a, b = np.searchsorted(tp, [t[0] - PLAN_SLACK_S, t[-1] + PLAN_SLACK_S])
        if b - a < 2:
            continue
        dist, plan_t = _project(t, x, y, sx[a:b], sy[a:b], tp[a:b])
        dev = t - plan_t
        q25, q50, q75 = np.percentile(dev, [25, 50, 75])
        d = float(np.median(dist))
        out.append({"tr_id": tr, "dist_m": d, "dev_s": float(q50), "spread_s": float(q75 - q25),
                    "score": d + DEV_WEIGHT * abs(q50) + SPREAD_WEIGHT * (q75 - q25)})
    return sorted(out, key=lambda c: c["score"])


def choose(ranked: list) -> dict | None:
    """Лучший кандидат, если он проходит пороги и заметно лучше второго; иначе None."""
    ok = [c for c in ranked if c["dist_m"] <= MAX_DIST_M and abs(c["dev_s"]) <= DEV_MAX_S
          and c["spread_s"] <= MAX_SPREAD_S]
    if not ok:
        return None
    best = ok[0]
    second = next((c for c in ranked if c["tr_id"] != best["tr_id"]), None)
    if second is not None and second["score"] - best["score"] < MARGIN:
        return None
    return best


def track(t, lat, lon, valid):
    """Последние WINDOW_S секунд достоверных отметок в метрах: (t, x, y) или None, если их мало или машина стоит."""
    t, lat, lon, valid = map(np.asarray, (t, lat, lon, valid))
    m = valid.astype(bool) & np.isfinite(lat) & np.isfinite(lon) & (t > t.max() - WINDOW_S)
    if m.sum() < MIN_FIXES:
        return None
    x, y = _xy(lat[m], lon[m])
    if np.hypot(np.diff(x), np.diff(y)).sum() < MIN_PATH_M:
        return None
    return t[m].astype(float), x, y


def match(t, lat, lon, valid, index: TripIndex, exclude=()) -> dict | None:
    """Рейс для трека машины: dict с tr_id и оценками или None, если однозначно определить нельзя.

    t — время отметок (шкала расписания), lat/lon — координаты, valid — признак достоверности.
    exclude — рейсы, уже занятые другими машинами."""
    tr = track(t, lat, lon, valid)
    return None if tr is None else choose(candidates(*tr, index, exclude))
