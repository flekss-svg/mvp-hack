from pathlib import Path

import pandas as pd
import pytest

from app.data_sources.mos_ru_schedule import DOW, MosRuScheduleSource, hhmmss_to_min


pytestmark = pytest.mark.unit


def write_mos_csv(path: Path, columns: list[str], rows: list[list[str]]) -> None:
    lines = [";".join(columns) + ";", ";".join(["ru"] * len(columns)) + ";"]
    lines.extend(";".join(row) + ";" for row in rows)
    path.write_text("\n".join(lines), encoding="utf-8")


def test_hhmmss_to_min_supports_service_days_over_24_hours() -> None:
    result = hhmmss_to_min(pd.Series(["03:30:00", "26:15:30"]))
    assert result.tolist() == [210.0, 1575.5]


def test_load_normalizes_mos_ru_csv_and_midnight_wrap(tmp_path: Path) -> None:
    datasets = {
        "routes": "routes",
        "stops": "stops",
        "trips": "trips",
        "stop_times": "times",
        "calendar": "calendar",
    }
    write_mos_csv(
        tmp_path / "data-routes-test.csv",
        ["Route code", "Agency code", "Number of the route", "Full name route", "Type of route"],
        [["r1", "a", "1", "Bus", "3"], ["r2", "a", "2", "Tram", "0"]],
    )
    write_mos_csv(
        tmp_path / "data-stops-test.csv",
        ["Stop code", "Stop name", "Transport type", "Centroid"],
        [["s1", "First", "bus", "[37.60, 55.75]"], ["s2", "Second", "bus", "[37.61, 55.76]"]],
    )
    write_mos_csv(
        tmp_path / "data-trips-test.csv",
        ["Route code", "Code list of dates", "Trip code", "Direction of trip"],
        [["r1", "svc", "t1", "0"], ["r2", "svc", "t2", "0"]],
    )
    write_mos_csv(
        tmp_path / "data-calendar-test.csv",
        ["Code list of dates", *DOW, "Start date of trip", "End date of trip"],
        [["svc", "1", "1", "1", "1", "1", "0", "0", "20260101", "20261231"]],
    )
    write_mos_csv(
        tmp_path / "data-times-test.csv",
        ["Trip code", "Arrival time", "Stop code", "Number stop"],
        [
            ["t1", "23:59:00", "s1", "1"],
            ["t1", "00:01:00", "s2", "2"],
            ["t2", "10:00:00", "s1", "1"],
            ["t2", "10:05:00", "s2", "2"],
        ],
    )

    tables = MosRuScheduleSource(tmp_path, datasets=datasets, n_routes=1).load()

    assert set(tables.routes["mode"]) == {"bus", "tram"}
    assert set(tables.trips["trip_id"]) == {"t1", "t2"}
    t1 = tables.stop_times[tables.stop_times["trip_id"] == "t1"]
    assert t1["arr_min"].tolist() == [1439.0, 1441.0]
    assert tables.stops["stop_id"].tolist() == ["s1", "s2"]


def test_missing_dataset_has_clear_error(tmp_path: Path) -> None:
    source = MosRuScheduleSource(tmp_path, datasets={}, n_routes=None)
    with pytest.raises(FileNotFoundError, match="Нет файла набора missing"):
        source._find("missing")
