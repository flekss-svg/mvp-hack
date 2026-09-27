"""Справочник «остановка -> маршруты» по ВСЕМУ расписанию data.mos.ru.

В данных организаторов нет номера маршрута — только tr_id машины и точки ее расписания с
координатами. Номер маршрута восстанавливается по тому, мимо остановок какого маршрута идет это
расписание (ml_service/routes.py). Для этого нужны все маршруты города, а не подвыборка
mos_ru_schedule.py (N_ROUTES) для режима «Симуляция».

Вход:  data/raw/data-<набор>-*.csv (наборы 60661, 60662, 60664, 60665), ~0,5 ГБ
Выход: data/processed/route_stops.parquet — одна строка на пару (маршрут, остановка), единицы МБ;
       лежит в репозитории, исходные CSV для работы сервиса не нужны.

Запуск: python3 -m app.data_sources.mos_ru_routes
"""
import pandas as pd

from app.data_sources.mos_ru_schedule import MosRuScheduleSource
from app.data_sources.processed_repository import save_route_stops

CHUNK_ROWS = 2_000_000   # плановое время на остановках — десятки миллионов строк, читаем частями


def build(source: MosRuScheduleSource | None = None) -> pd.DataFrame:
    src = source or MosRuScheduleSource(n_routes=None)
    routes = src._read(src.datasets["routes"], ["Route code", "Number of the route", "Full name route",
                                                 "Type of route"])
    routes.columns = ["route_id", "route_short_name", "route_long_name", "route_type"]
    routes["mode"] = routes["route_type"].map({"3": "bus", "0": "tram", "5": "trolley"}).fillna("other")

    stops = src._read(src.datasets["stops"], ["Stop code", "Stop name", "Centroid"])
    xy = stops["Centroid"].str.extract(r"\[([\d.]+),\s*([\d.]+)\]").astype(float)
    stops = pd.DataFrame({"stop_id": stops["Stop code"], "stop_name": stops["Stop name"],
                          "stop_lon": xy[0], "stop_lat": xy[1]}).dropna(subset=["stop_lon", "stop_lat"])

    trips = src._read(src.datasets["trips"], ["Trip code", "Route code"])
    route_of_trip = dict(zip(trips["Trip code"], trips["Route code"]))

    pairs = set()
    for chunk in pd.read_csv(src._find(src.datasets["stop_times"]), sep=";", skiprows=[1], dtype=str,
                             usecols=["Trip code", "Stop code"], chunksize=CHUNK_ROWS):
        route = chunk["Trip code"].map(route_of_trip)
        pairs.update(zip(route[route.notna()], chunk.loc[route.notna(), "Stop code"]))

    out = (pd.DataFrame(sorted(pairs), columns=["route_id", "stop_id"])
           .merge(routes[["route_id", "route_short_name", "route_long_name", "mode"]], on="route_id")
           .merge(stops, on="stop_id"))
    return out[["route_id", "route_short_name", "route_long_name", "mode",
                "stop_id", "stop_name", "stop_lon", "stop_lat"]]


def main() -> None:
    table = build()
    save_route_stops(table)
    print(f"маршрутов {table.route_id.nunique():,}, остановок {table.stop_id.nunique():,}, "
          f"пар маршрут-остановка {len(table):,}")


if __name__ == "__main__":
    main()
