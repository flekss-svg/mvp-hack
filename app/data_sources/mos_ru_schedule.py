"""Адаптер data.mos.ru -> каноническая схема расписания (domain.schema.ScheduleTables).

Это единственный файл, который нужно менять, если поменяется формат выгрузки data.mos.ru
(другие названия колонок, другие коды наборов) или появится другой источник планового
расписания (например, GTFS другого города) — тогда рядом появляется новый класс,
реализующий тот же протокол ScheduleSource (см. data_sources/base.py), а движок признаков,
модель и сервис не меняются вовсе.

Вход:  data/raw/data-<номер набора>-*.csv
Выход: ScheduleTables (routes, stops, trips, stop_times, calendar), сохраняется через
       processed_repository.save_schedule_tables().
"""
import pandas as pd

from app.config import DATASETS, N_ROUTES, RAW
from app.data_sources.processed_repository import save_schedule_tables
from app.domain.schema import ScheduleTables

DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def hhmmss_to_min(s: pd.Series) -> pd.Series:
    """'26:15:00' -> 1575.0 (минуты от начала служебных суток, может быть > 1440)."""
    p = s.str.split(":", expand=True).astype(int)
    return p[0] * 60 + p[1] + p[2] / 60


class MosRuScheduleSource:
    """Реализация ScheduleSource поверх выгрузок data.mos.ru (наборы 60661/60662/60664/60665/60666)."""

    def __init__(self, raw_dir=RAW, datasets: dict = DATASETS, n_routes: int | None = N_ROUTES):
        self.raw_dir = raw_dir
        self.datasets = datasets
        self.n_routes = n_routes

    def _find(self, num: str):
        files = sorted(self.raw_dir.glob(f"data-{num}-*.csv"))
        if not files:
            raise FileNotFoundError(f"Нет файла набора {num} в {self.raw_dir}")
        return files[-1]

    def _read(self, num: str, usecols=None) -> pd.DataFrame:
        # У data.mos.ru две строки заголовка (EN + RU) и лишний ';' в конце строки
        df = pd.read_csv(self._find(num), sep=";", skiprows=[1], dtype=str, usecols=usecols)
        return df.loc[:, ~df.columns.str.startswith("Unnamed")]

    def load(self) -> ScheduleTables:
        routes = self._read(self.datasets["routes"]).rename(columns={
            "Route code": "route_id", "Agency code": "agency_id", "Number of the route": "route_short_name",
            "Full name route": "route_long_name", "Type of route": "route_type"})
        routes = routes[["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"]]
        routes["mode"] = routes["route_type"].map({"3": "bus", "0": "tram", "5": "trolley"}).fillna("other")

        stops = self._read(self.datasets["stops"], ["Stop code", "Stop name", "Transport type", "Centroid"])
        xy = stops["Centroid"].str.extract(r"\[([\d.]+),\s*([\d.]+)\]").astype(float)
        stops = pd.DataFrame({"stop_id": stops["Stop code"], "stop_name": stops["Stop name"],
                              "stop_lon": xy[0], "stop_lat": xy[1], "modes": stops["Transport type"]})

        trips = self._read(self.datasets["trips"], ["Route code", "Code list of dates", "Trip code", "Direction of trip"])
        trips.columns = ["route_id", "service_id", "trip_id", "direction_id"]

        cal = self._read(self.datasets["calendar"])
        cal = cal.rename(columns={"Code list of dates": "service_id",
                                  "Start date of trip": "start_date", "End date of trip": "end_date"})
        for d in DOW:
            cal[d] = cal[d].astype(int)
        cal = cal[["service_id", *DOW, "start_date", "end_date"]]

        st = self._read(self.datasets["stop_times"], ["Trip code", "Arrival time", "Stop code", "Number stop"])
        st.columns = ["trip_id", "arrival", "stop_id", "stop_sequence"]

        # --- подвыборка маршрутов для MVP: самые насыщенные по будням ---
        weekday_services = set(cal.loc[cal["Monday"] == 1, "service_id"])
        wk = trips[trips["service_id"].isin(weekday_services)]
        counts = wk.groupby("route_id").size().sort_values(ascending=False)
        keep = counts.index[: self.n_routes] if self.n_routes else counts.index
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

        return ScheduleTables(routes=routes, stops=stops, trips=trips, stop_times=st, calendar=cal)


def main():
    tables = MosRuScheduleSource().load()
    save_schedule_tables(tables)
    for name, df in [("routes", tables.routes), ("stops", tables.stops), ("trips", tables.trips),
                     ("stop_times", tables.stop_times), ("calendar", tables.calendar)]:
        print(f"{name:11s} {len(df):>9,} строк")


if __name__ == "__main__":
    main()
