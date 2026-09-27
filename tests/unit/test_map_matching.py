"""Map matching: рейс по треку. Три нитки по одной и той же линии — различать их должно время."""
import numpy as np
import pandas as pd
import pytest

from ml_service import map_matching as mm

pytestmark = pytest.mark.unit

T0 = 36_000
STEP_DEG = 0.0045          # ~500 м между остановками, остановка раз в минуту -> ~8 м/с


def thread(tr: str, shift: int = 0, reverse: bool = False) -> pd.DataFrame:
    k = np.arange(40)
    lat = 55.70 + STEP_DEG * (k[::-1] if reverse else k)
    return pd.DataFrame({"tt_action_item_id": [f"{tr}-{i}" for i in k], "tr_id": tr,
                         "t_plan": T0 + shift + 60 * k, "s_lat": lat, "s_lon": 37.60})


@pytest.fixture
def index() -> mm.TripIndex:
    # A и B — одна линия с разницей 15 минут по графику, R — та же линия в обратную сторону
    return mm.TripIndex(pd.concat([thread("A"), thread("B", shift=900), thread("R", reverse=True)]))


def along(start: int, delay: int = 0, reverse: bool = False, n: int = 60, step: int = 10):
    """Трек, идущий по графику нитки, начавшейся в start, с опозданием delay секунд."""
    t = np.arange(start + 300, start + 300 + n * step, step, dtype=float)
    k = (t - delay - start) / 60
    lat = 55.70 + STEP_DEG * (39 - k if reverse else k)
    return t, lat, np.full_like(t, 37.60), np.ones_like(t, dtype=bool)


def test_time_separates_vehicles_on_the_same_line(index) -> None:
    assert mm.match(*along(T0, delay=90), index)["tr_id"] == "A"
    assert mm.match(*along(T0 + 900, delay=-40), index)["tr_id"] == "B"


def test_direction_is_taken_into_account(index) -> None:
    assert mm.match(*along(T0, reverse=True), index)["tr_id"] == "R"


def test_estimated_deviation_from_schedule(index) -> None:
    assert mm.match(*along(T0, delay=120), index)["dev_s"] == pytest.approx(120, abs=15)


def test_no_match_far_from_every_route(index) -> None:
    t, lat, lon, valid = along(T0)
    assert mm.match(t, lat + 0.05, lon, valid, index) is None


def test_no_match_for_a_standing_vehicle(index) -> None:
    t, lat, lon, valid = along(T0)
    assert mm.match(t, np.full_like(lat, lat[0]), lon, valid, index) is None


def test_taken_trip_is_not_given_to_another_vehicle(index) -> None:
    # рейс A уже занят другой машиной; B отстает по графику на 15 минут — это не повод выбрать его
    assert mm.match(*along(T0), index, exclude={"A"}) is None


def test_invalid_fixes_are_ignored(index) -> None:
    t, lat, lon, valid = along(T0)
    valid = np.zeros_like(valid)
    assert mm.match(t, lat, lon, valid, index) is None
