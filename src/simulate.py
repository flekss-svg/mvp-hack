"""Синтетический «факт» движения на основе реального планового расписания Москвы.

ВАЖНО: это заглушка на время, пока нет реальной телематики. Модуль генерирует фактическое
время прохождения остановок с правдоподобной механикой сбоев:
  * часы пик и «узкие» перегоны (у каждого перегона своя скрытая чувствительность к трафику);
  * дождь (погода известна диспетчеру, это легальный признак);
  * инциденты: перегон «встает» на 15–50 минут (ДТП, ремонт) — их модель должна
    замечать по машинам, которые уже прошли этот перегон;
  * эффект «пачки»: чем больше разрыв с впереди идущей машиной, тем дольше посадка;
  * водитель немного нагоняет при опоздании и не уезжает раньше графика.

Когда появятся реальные данные, этот модуль не нужен: ingest.py превращает GPS-отметки
в тот же формат «рейс — остановка — план — факт».

Выход: data/processed/fact/day=YYYY-MM-DD.parquet и data/processed/sim_meta.parquet
"""
import math
import random

import numpy as np
import pandas as pd

from config import PROC, SIM_START, SIM_DAYS, RANDOM_SEED

trips_service = {}  # trip_id -> service_id
DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def peak(h: float, weekend: bool) -> float:
    p = math.exp(-((h - 8.3) / 1.3) ** 2) + 0.9 * math.exp(-((h - 18.2) / 1.6) ** 2)
    return p * (0.4 if weekend else 1.0)


def active_services(cal: pd.DataFrame, trips: pd.DataFrame, date: pd.Timestamp) -> set:
    """Перечни дат, действующие в этот день. Старые перечни в выгрузке не закрыты датой
    окончания, поэтому по каждому маршруту берем только самую свежую редакцию."""
    d = date.strftime("%Y%m%d")
    m = (cal[DOW[date.dayofweek]] == 1) & (cal["start_date"] <= d) & (cal["end_date"] >= d)
    act = cal.loc[m, ["service_id", "start_date"]]
    rs = trips[["route_id", "service_id"]].drop_duplicates().merge(act, on="service_id")
    latest = rs.groupby("route_id")["start_date"].transform("max")
    return set(rs.loc[rs["start_date"] == latest, "service_id"])


def build_trip_table(trips, st):
    """trip_id -> (route_id, dir, stops[], plan[])"""
    g = st.groupby("trip_id", sort=False)
    stops = g["stop_id"].apply(list)
    plan = g["arr_min"].apply(list)
    t = trips.set_index("trip_id")
    return {tid: (t.at[tid, "route_id"], t.at[tid, "direction_id"], stops[tid], plan[tid])
            for tid in stops.index}


def main():
    rng = random.Random(RANDOM_SEED)
    trips = pd.read_parquet(PROC / "trips.parquet")
    st = pd.read_parquet(PROC / "stop_times.parquet")
    cal = pd.read_parquet(PROC / "calendar.parquet")
    table = build_trip_table(trips, st)
    trips_service.update(dict(zip(trips.trip_id, trips.service_id)))

    # скрытая чувствительность перегонов к трафику (модель ее не видит напрямую)
    segs = set()
    for _, _, s, _ in table.values():
        segs.update(zip(s[:-1], s[1:]))
    segs = sorted(segs)
    sens = {}
    for sg in segs:
        b = rng.lognormvariate(0, 0.6)
        if rng.random() < 0.05:
            b *= 3.0  # хронически проблемный перегон
        sens[sg] = min(b, 4.0)
    seg_list = segs

    out_dir = PROC / "fact"
    out_dir.mkdir(exist_ok=True)
    meta = []

    for d in range(SIM_DAYS):
        date = pd.Timestamp(SIM_START) + pd.Timedelta(days=d)
        weekend = date.dayofweek >= 5
        services = active_services(cal, trips, date)
        # погода дня
        rain, r0, r1 = 0.0, 0.0, 0.0
        if rng.random() < 0.25:
            rain = rng.uniform(0.3, 1.0)
            r0 = rng.uniform(5 * 60, 18 * 60)
            r1 = r0 + rng.uniform(3 * 60, 8 * 60)

        # инциденты дня
        incidents = {}
        for _ in range(np.random.default_rng(RANDOM_SEED + d).poisson(12)):
            sg = seg_list[rng.randrange(len(seg_list))]
            t0 = rng.uniform(7 * 60, 22 * 60)
            incidents.setdefault(sg, []).append((t0, t0 + rng.uniform(15, 50), rng.uniform(2, 7)))

        meta.append(dict(date=date.date().isoformat(), rain=rain, rain_from=r0, rain_to=r1,
                         n_incidents=sum(len(v) for v in incidents.values())))
        rows = _simulate_day(rng, date, weekend, services, table, sens, incidents,
                                   rain, r0, r1)
        df = pd.DataFrame(rows, columns=["trip_id", "route_id", "direction_id", "k",
                                               "stop_id", "plan", "fact"])
        df["date"] = date.date().isoformat()
        df.to_parquet(out_dir / f"day={date.date()}.parquet", index=False)
        print(f"{date.date()} {'вых' if weekend else 'будн'} рейсов: {df.trip_id.nunique():>6,}"
              f"  событий: {len(df):>8,}  ср. задержка: {(df.fact - df.plan).mean():5.2f} мин"
              f"  дождь: {rain:.1f}  инцидентов: {meta[-1]['n_incidents']}")

    pd.DataFrame(meta).to_parquet(PROC / "sim_meta.parquet", index=False)


def _simulate_day(rng, date, weekend, services, table, sens, incidents, rain, r0, r1):
    rows = []
    # рейсы дня, сгруппированные по маршруту и направлению, по порядку отправления
    groups = {}
    for tid, (rid, dr, stops, plan) in table.items():
        if trips_service[tid] in services:
            groups.setdefault((rid, dr), []).append((plan[0], tid))

    for (rid, dr), lst in groups.items():
        lst.sort()
        last_pass = {}  # stop_id -> (fact, plan) предыдущей машины этого маршрута/направления
        for _, tid in lst:
            _, _, stops, plan = table[tid]
            # отправление с конечной
            dev = rng.gauss(0.2, 0.5)
            if rng.random() < 0.04:
                dev += rng.expovariate(1 / 5)
            a = plan[0] + max(dev, -0.5)
            facts = [a]
            for k in range(1, len(stops)):
                s = max(plan[k] - plan[k - 1], 0.3)
                sg = (stops[k - 1], stops[k])
                b = sens[sg]
                h = (a / 60.0) % 24
                f = 1 + 0.18 * peak(h, weekend) * b
                if rain and r0 <= a <= r1:
                    f += 0.12 * rain * math.sqrt(b)
                run = s * f + rng.gauss(0, 0.07 * s + 0.08)
                delay = a - plan[k - 1]
                if delay > 1:
                    run *= 0.95  # водитель нагоняет
                for t0, t1, extra in incidents.get(sg, ()):
                    if t0 <= a <= t1:
                        run += extra * rng.uniform(0.7, 1.3)
                a = a + max(run, 0.3 * s)
                # посадка: эффект пачки
                lp = last_pass.get(stops[k])
                if lp is not None and 0 < plan[k] - lp[1] < 30:
                    gap = (a - lp[0]) - (plan[k] - lp[1])
                    if gap > 0:
                        a += min(0.08 * gap, 0.5)
                # не уезжаем раньше графика больше чем на 0.5 мин
                a = max(a, plan[k] - 0.5)
                facts.append(a)
            for k, stp in enumerate(stops):
                last_pass[stp] = (facts[k], plan[k])
                rows.append((tid, rid, dr, k, stp, plan[k], facts[k]))
    return rows


if __name__ == "__main__":
    main()
