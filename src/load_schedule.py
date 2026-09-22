"""Загрузка планового расписания Москвы (data.mos.ru) и приведение к GTFS-подобной схеме.

Вход:  data/raw/data-<номер набора>-*.csv
Выход: data/processed/{routes,stops,trips,stop_times,calendar}.parquet
"""
import re
import pandas as pd

from config import RAW, PROC, DATASETS, N_ROUTES

DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _find(num: str):
    files = sorted(RAW.glob(f"data-{num}-*.csv"))
    if not files:
        raise FileNotFoundError(f"Нет файла набора {num} в {RAW}")
    return files[-1]


def _read(num: str, usecols=None) -> pd.DataFrame:
    # У data.mos.ru две строки заголовка (EN + RU) и лишний ';' в конце строки
    df = pd.read_csv(_find(num), sep=";", skiprows=[1], dtype=str, usecols=usecols)
    return df.loc[:, ~df.columns.str.startswith("Unnamed")]


def hhmmss_to_min(s: pd.Series) -> pd.Series:
    """'26:15:00' -> 1575.0 (минуты от начала служебных суток, может быть > 1440)."""
    p = s.str.split(":", expand=True).astype(int)
    return p[0] * 60 + p[1] + p[2] / 60


def load():
    PROC.mkdir(parents=True, exist_ok=True)

    routes = _read(DATASETS["routes"]).rename(columns={
        "Route code": "route_id", "Agency code": "agency_id", "Number of the route": "route_short_name",
        "Full name route": "route_long_name", "Type of route": "route_type"})
    routes = routes[["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"]]
    routes["mode"] = routes["route_type"].map({"3": "bus", "0": "tram", "5": "trolley"}).fillna("other")

    stops = _read(DATASETS["stops"], ["Stop code", "Stop name", "Transport type", "Centroid"])
    xy = stops["Centroid"].str.extract(r"\[([\d.]+),\s*([\d.]+)\]").astype(float)
    stops = pd.DataFrame({"stop_id": stops["Stop code"], "stop_name": stops["Stop name"],
                          "stop_lon": xy[0], "stop_lat": xy[1], "modes": stops["Transport type"]})

    trips = _read(DATASETS["trips"], ["Route code", "Code list of dates", "Trip code", "Direction of trip"])
    trips.columns = ["route_id", "service_id", "trip_id", "direction_id"]

    cal = _read(DATASETS["calendar"])
    cal = cal.rename(columns={"Code list of dates": "service_id",
                              "Start date of trip": "start_date", "End date of trip": "end_date"})
    for d in DOW:
        cal[d] = cal[d].astype(int)
    cal = cal[["service_id", *DOW, "start_date", "end_date"]]

    st = _read(DATASETS["stop_times"], ["Trip code", "Arrival time", "Stop code", "Number stop"])
    st.columns = ["trip_id", "arrival", "stop_id", "stop_sequence"]

    # --- подвыборка маршрутов для MVP: самые насыщенные по будням ---
    weekday_services = set(cal.loc[cal["Monday"] == 1, "service_id"])
    wk = trips[trips["service_id"].isin(weekday_services)]
    counts = wk.groupby("route_id").size().sort_values(ascending=False)
    keep = counts.index[:N_ROUTES] if N_ROUTES else counts.index
    # в MVP гарантированно добавляем трамваи — у них самые предсказуемые «узкие места»
    trams = routes.loc[routes["mode"] == "tram", "route_id"]
    keep = set(keep) | set(trams[trams.isin(counts.index)][:10])

    trips = trips[trips["route_id"].isin(keep)]
    st = st[st["trip_id"].isin(set(trips["trip_id"]))].copy()
    st["arr_min"] = hhmmss_to_min(st["arrival"])
    st["stop_sequence"] = st["stop_sequence"].astype(int)
    st = st.drop(columns="arrival").sort_values(["trip_id", "stop_sequence"])
    # редкие рейсы, где время «перескакивает» через полночь (23:59 -> 00:01): приводим к 24:01
    for _ in range(2):
        jump = st.groupby("trip_id")["arr_min"].diff() < -720
        wrap = jump.groupby(st["trip_id"]).cumsum() > 0
        st.loc[wrap, "arr_min"] += 1440
    st = st[st["stop_id"].isin(set(stops["stop_id"]))]

    routes = routes[routes["route_id"].isin(keep)]
    stops = stops[stops["stop_id"].isin(set(st["stop_id"]))]

    for name, df in dict(routes=routes, stops=stops, trips=trips, calendar=cal, stop_times=st).items():
        df.to_parquet(PROC / f"{name}.parquet", index=False)
        print(f"{name:11s} {len(df):>9,} строк")


if __name__ == "__main__":
    load()
