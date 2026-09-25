"""Адаптер телематики: GPS-отметки -> события «машина прошла остановку»
(domain.schema.STOP_EVENT_COLUMNS).

Это единственное место, которое нужно переписать под реальные данные организаторов.
Все остальное (engine, model, service, дашборд) работает с событиями в канонической схеме
и не знает, откуда они пришли — из этого адаптера или из simulation/synthetic_telemetry.py.

Ожидаемая схема отметки (Ping) после декодирования протокола:
    vehicle_id, trip_id, route_id, direction_id, ts_min, lat, lon, speed
ts_min — минуты от начала служебных суток (03:00 = 180).

NDTP: байты разбирает data_sources/ndtp_protocol.py, соединения принимает
service/ndtp_server.py. NDTP-пакет не содержит trip_id — только номер устройства
(unit_id), координаты, время и скорость. Рейс нужно восстановить по наряду/выходу или
сопоставлением «маршрут + направление + ближайший плановый рейс».
"""
import math

import numpy as np
import pandas as pd

from app.domain.schema import STOP_EVENT_COLUMNS

STOP_RADIUS_M = 60.0


def _dist_m(lat1, lon1, lat2, lon2):
    kx = 111_320 * math.cos(math.radians(55.75))
    return math.hypot((lon1 - lon2) * kx, (lat1 - lat2) * 110_540)


def pings_to_events(pings: pd.DataFrame, schedule: dict, stops_xy: dict) -> pd.DataFrame:
    """Привязка отметок к остановкам рейса (упрощенный map-matching).

    Для каждой остановки рейса берем момент максимального сближения с ней. Если отметки
    редкие и машина «перепрыгнула» остановку, время интерполируем между соседними.

    Возвращает DataFrame с колонками domain.schema.STOP_EVENT_COLUMNS.
    """
    out = []
    for trip_id, g in pings.sort_values("ts_min").groupby("trip_id", sort=False):
        stops, plan = schedule[trip_id]
        xy = [stops_xy[s] for s in stops]
        ts, la, lo = g["ts_min"].to_numpy(), g["lat"].to_numpy(), g["lon"].to_numpy()
        k, best_d, best_t = 0, float("inf"), None
        times = [None] * len(stops)
        for t, a, o in zip(ts, la, lo):
            while k < len(stops):
                d = _dist_m(a, o, xy[k][1], xy[k][0])
                d_next = (_dist_m(a, o, xy[k + 1][1], xy[k + 1][0])
                          if k + 1 < len(stops) else float("inf"))
                if d < best_d:
                    best_d, best_t = d, t
                # остановка пройдена: удаляемся от нее и ближе к следующей
                if best_d < STOP_RADIUS_M and (d > best_d + 15 or d_next < d):
                    times[k] = best_t
                    k, best_d, best_t = k + 1, float("inf"), None
                    continue
                if best_d >= STOP_RADIUS_M and d_next < d and d_next < STOP_RADIUS_M * 2:
                    k, best_d, best_t = k + 1, float("inf"), None  # пропуск, восстановим ниже
                    continue
                break
        if k < len(stops) and best_d < STOP_RADIUS_M:
            times[k] = best_t
        # интерполяция пропущенных остановок по плану
        known = [i for i, v in enumerate(times) if v is not None]
        if len(known) < 2:
            continue
        filled = np.interp(range(len(stops)), known, [times[i] for i in known])
        first, last = known[0], known[-1]
        meta = g.iloc[0]
        for i in range(first, last + 1):
            out.append((trip_id, meta["route_id"], meta["direction_id"], i, stops[i],
                        plan[i], float(filled[i])))
    return pd.DataFrame(out, columns=STOP_EVENT_COLUMNS)


def synth_pings(events: pd.DataFrame, stops_xy: dict, every_sec=20, noise_m=12, seed=0):
    """Обратная операция для проверки адаптера: из событий делаем GPS-трек с шумом."""
    rng = np.random.default_rng(seed)
    rows = []
    for trip_id, g in events.sort_values(["trip_id", "k"]).groupby("trip_id", sort=False):
        f = g["fact"].to_numpy()
        lon = np.array([stops_xy[s][0] for s in g["stop_id"]])
        lat = np.array([stops_xy[s][1] for s in g["stop_id"]])
        t = np.arange(f[0], f[-1], every_sec / 60)
        # машина стоит у остановки ~20 сек, между остановками едет равномерно
        pos_lon, pos_lat = np.interp(t, f, lon), np.interp(t, f, lat)
        pos_lat += rng.normal(0, noise_m / 110_540, len(t))
        pos_lon += rng.normal(0, noise_m / 63_000, len(t))
        r = g.iloc[0]
        for a, b, c in zip(t, pos_lat, pos_lon):
            rows.append((r.trip_id, r.trip_id, r.route_id, r.direction_id, a, b, c))
    return pd.DataFrame(rows, columns=["vehicle_id", "trip_id", "route_id", "direction_id",
                                       "ts_min", "lat", "lon"])


def _self_test():
    """Самопроверка адаптера на синтетическом треке: события -> GPS -> события, сверяем ошибку."""
    from app.data_sources import processed_repository as repo
    from app.engine.stream_state import load_schedule_index

    schedule = load_schedule_index(repo.read_stop_times())
    stops = repo.read_stops()
    stops_xy = dict(zip(stops.stop_id, zip(stops.stop_lon, stops.stop_lat)))
    ev = repo.read_fact_day(repo.list_fact_days()[-1])
    sample = ev[ev.trip_id.isin(ev.trip_id.drop_duplicates().sample(300, random_state=1))]
    pings = synth_pings(sample, stops_xy)
    rec = pings_to_events(pings, schedule, stops_xy)
    m = sample.merge(rec, on=["trip_id", "k"], suffixes=("", "_rec"))
    err = (m.fact - m.fact_rec).abs() * 60
    print(f"Проверка адаптера на 300 рейсах: {len(pings):,} GPS-отметок -> {len(rec):,} событий")
    print(f"Восстановлено остановок: {len(m) / len(sample):.1%}")
    print(f"Ошибка времени прохождения: медиана {err.median():.0f} с, 90% {err.quantile(.9):.0f} с")


if __name__ == "__main__":
    _self_test()
