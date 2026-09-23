"""Единая точка доступа к обработанным данным на диске (data/processed/*.parquet).

Если формат хранения изменится (например, parquet -> база данных), достаточно поправить
этот файл — остальной код обращается только к этим функциям, а не к путям и именам файлов
напрямую.
"""
from pathlib import Path

import pandas as pd

from app.config import PROC
from app.domain.schema import ScheduleTables

FACT_DIR = PROC / "fact"


# ---------- плановое расписание ----------

def save_schedule_tables(tables: ScheduleTables) -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    tables.routes.to_parquet(PROC / "routes.parquet", index=False)
    tables.stops.to_parquet(PROC / "stops.parquet", index=False)
    tables.trips.to_parquet(PROC / "trips.parquet", index=False)
    tables.stop_times.to_parquet(PROC / "stop_times.parquet", index=False)
    tables.calendar.to_parquet(PROC / "calendar.parquet", index=False)


def read_schedule_tables() -> ScheduleTables:
    return ScheduleTables(
        routes=read_routes(), stops=read_stops(), trips=read_trips(),
        stop_times=read_stop_times(), calendar=read_calendar())


def read_routes() -> pd.DataFrame:
    return pd.read_parquet(PROC / "routes.parquet")


def read_stops() -> pd.DataFrame:
    return pd.read_parquet(PROC / "stops.parquet")


def read_trips() -> pd.DataFrame:
    return pd.read_parquet(PROC / "trips.parquet")


def read_stop_times() -> pd.DataFrame:
    return pd.read_parquet(PROC / "stop_times.parquet")


def read_calendar() -> pd.DataFrame:
    return pd.read_parquet(PROC / "calendar.parquet")


def route_mode_map(routes: pd.DataFrame) -> dict:
    """route_id -> "bus" | "tram" | "trolley" | "other"."""
    return dict(zip(routes.route_id, routes["mode"]))


def route_name_map(routes: pd.DataFrame) -> dict:
    """route_id -> короткое имя маршрута для показа диспетчеру."""
    return dict(zip(routes.route_id, routes.route_short_name))


# ---------- фактическое движение (симулятор или реальная телематика) ----------

def save_fact_day(events: pd.DataFrame, date) -> None:
    FACT_DIR.mkdir(parents=True, exist_ok=True)
    events.to_parquet(FACT_DIR / f"day={date}.parquet", index=False)


def list_fact_days() -> list[Path]:
    return sorted(FACT_DIR.glob("day=*.parquet"))


def read_fact_day(path) -> pd.DataFrame:
    return pd.read_parquet(path)


def fact_day_date(path) -> str:
    """Дата (YYYY-MM-DD) из имени файла day=YYYY-MM-DD.parquet."""
    return str(path).split("day=")[1][:10]


def save_sim_meta(meta: pd.DataFrame) -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    meta.to_parquet(PROC / "sim_meta.parquet", index=False)


def read_sim_meta() -> pd.DataFrame:
    """Индексировано по дате (строка YYYY-MM-DD)."""
    return pd.read_parquet(PROC / "sim_meta.parquet").set_index("date")
