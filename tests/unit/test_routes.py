"""Номер маршрута машины хакатона по остановкам ее расписания (ml_service/routes.py)."""
import numpy as np
import pandas as pd
import pytest

from ml_service.routes import load_route_stops, match_routes

pytestmark = pytest.mark.unit


def route_stops() -> pd.DataFrame:
    """Два маршрута: у м17 восемь остановок вдоль меридиана, у 21 — только две первые из них и свои."""
    rows = [("r17", "м17", "Щукинская — Строгино", "bus", f"s{i}", 55.70 + 0.004 * i, 37.60) for i in range(8)]
    rows += [("r21", "21", "Сокол — Тушино", "bus", f"s{i}", 55.70 + 0.004 * i, 37.60) for i in range(2)]
    rows += [("r21", "21", "Сокол — Тушино", "bus", f"t{i}", 55.70, 37.70 + 0.004 * i) for i in range(6)]
    return pd.DataFrame(rows, columns=["route_id", "route_short_name", "route_long_name", "mode",
                                       "stop_id", "stop_lat", "stop_lon"])


def plan(tr: str, lats, lons) -> pd.DataFrame:
    return pd.DataFrame({"tr_id": tr, "s_lat": lats, "s_lon": lons})


def test_route_is_the_one_whose_stops_cover_the_schedule() -> None:
    lat = 55.70 + 0.004 * np.arange(8) + 0.0002          # ~20 м от остановок
    out = match_routes(plan("tr1", lat, 37.60), route_stops())
    assert out == {"tr1": {"route": "м17", "route_name": "Щукинская — Строгино", "mode": "bus"}}


def test_ambiguous_or_off_stop_schedules_get_no_route() -> None:
    # две общие остановки — у обоих маршрутов одинаковое покрытие: номер не ставим
    shared = plan("tr2", 55.70 + 0.004 * np.arange(2), 37.60)
    far = plan("tr3", [56.5, 56.6], [38.5, 38.6])        # ни одной остановки рядом
    assert match_routes(pd.concat([shared, far]), route_stops()) == {}


def test_missing_lookup_means_no_routes(tmp_path) -> None:
    assert load_route_stops(tmp_path / "nope.parquet") is None
    assert match_routes(plan("tr1", [55.7], [37.6]), None) == {}
