"""Канонические структуры данных — единый язык между источниками данных, движком признаков,
моделью и сервисом.

Если формат входных данных изменится (другие колонки в выгрузке, другой протокол
телематики, другой город), достаточно поправить адаптер в data_sources/ или simulation/,
который приводит сырые данные к этим структурам. Engine, model и service от конкретного
источника не зависят и знают только эту схему.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypedDict, Union

import pandas as pd


class StopEvent(TypedDict):
    """Событие «машина прошла остановку» — единственный входной формат для engine.* и model.*.

    Не важно, откуда оно взялось: из синтетического симулятора (simulation/) или из
    реальной телематики (data_sources/gps_telemetry.py) — колонки всегда одни и те же.
    """

    trip_id: str
    route_id: str
    direction_id: str
    k: int              # порядковый номер остановки в рейсе, считая с 0
    stop_id: str
    plan: float          # плановое время прохождения, минуты от начала служебных суток
    fact: float           # фактическое время прохождения, минуты от начала служебных суток


# Колонки, которые обязана содержать таблица событий (DataFrame) на выходе любого адаптера
# телематики. engine.stream_state.run_day() и StreamState.features()/.update() полагаются
# именно на этот набор колонок, а не на то, откуда пришли данные.
STOP_EVENT_COLUMNS = ["trip_id", "route_id", "direction_id", "k", "stop_id", "plan", "fact"]


class DayContext(TypedDict):
    """Контекст дня, который движок признаков учитывает как есть — не важно, взята погода
    из симулятора или из реального прогноза (Open-Meteo и т.п.)."""

    dow: int
    weekend: int
    holiday: int
    rain: Union[float, Callable[[float], float]]


class RiskPrediction(TypedDict):
    """Текущий прогноз риска по одному рейсу — то, что отдает GET /risk."""

    trip_id: str
    route: str
    stop_id: str
    t: float
    delay_now: float
    risk: float


@dataclass
class ScheduleTables:
    """Плановое расписание в канонической, GTFS-подобной схеме.

    Про конкретный источник (data.mos.ru, GTFS другого города, ...) знает только адаптер
    в data_sources/, который эти таблицы строит — весь остальной код от него не зависит.

    routes:     route_id, agency_id, route_short_name, route_long_name, route_type, mode
    stops:      stop_id, stop_name, stop_lon, stop_lat, modes
    trips:      trip_id, route_id, service_id, direction_id
    stop_times: trip_id, stop_id, stop_sequence, arr_min
    calendar:   service_id, Monday..Sunday, start_date, end_date
    """

    routes: pd.DataFrame
    stops: pd.DataFrame
    trips: pd.DataFrame
    stop_times: pd.DataFrame
    calendar: pd.DataFrame
