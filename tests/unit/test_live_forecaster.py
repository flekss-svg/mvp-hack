"""Прогнозист живого потока на заглушках моделей: проверяем логику вокруг моделей, а не сами модели."""
import numpy as np
import pandas as pd
import pytest

import ml_service.live as live
from app.data_sources.ndtp_protocol import Fix
from ml_service.live import STALE_S, LiveForecaster

pytestmark = pytest.mark.unit

T0 = 2000


class StubRegressor:
    feature_names_ = ["cur_dev_s", "horizon_s"]

    def predict(self, X):
        return np.full(len(X), 42.0)


def plan_for(tr: str) -> pd.DataFrame:
    """Остановка каждую минуту, ~500 м друг от друга по прямой на север."""
    k = np.arange(40)
    return pd.DataFrame({"tt_action_item_id": [f"{tr}-{i}" for i in k], "tr_id": tr, "t_plan": T0 + 60 * k,
                         "s_lat": 55.70 + 0.0045 * k, "s_lon": 37.60})


def make(monkeypatch, **kw) -> LiveForecaster:
    monkeypatch.setattr(live, "predict_class_probs",
                        lambda X, clf: pd.DataFrame({"early": [0.1], "ontime": [0.6], "late": [0.3]}))
    monkeypatch.setattr(live, "explain", lambda X, top_k, model: [["причина"]])
    plan = pd.concat([plan_for("trA"), plan_for("trB")]).sort_values(["tr_id", "t_plan"])
    return LiveForecaster(plan, {1: "trA", 2: "trB", 99: "no-plan"}, {"trA-13": "Остановка 13"},
                          StubRegressor(), None, min_interval_s=0, **kw)


def fix(unit: int, t: int, lat: float = 55.70, valid: bool = True, speed: int = 20) -> Fix:
    return Fix(unit, t, 0.0, 37.60, lat, valid, speed, 0)


def feed(fc: LiveForecaster, unit: int, t_from: int, t_to: int, step: int = 10) -> None:
    for t in range(t_from, t_to + 1, step):
        fc.ingest(fix(unit, t, lat=55.70 + (t - T0) * 0.0001))


def test_units_without_a_schedule_are_ignored_and_duplicates_dropped(monkeypatch) -> None:
    fc = make(monkeypatch)
    assert fc.units == {1, 2}                       # 99 не в расписании
    assert fc.ingest(fix(99, T0)) is False
    assert fc.ingest(fix(1, T0)) is True
    assert fc.ingest(fix(1, T0)) is False           # повтор
    assert fc.ingest(fix(1, T0 - 5)) is False       # опоздавший пакет


def test_target_is_the_first_stop_in_the_10_to_15_minute_window(monkeypatch) -> None:
    fc = make(monkeypatch)
    feed(fc, 1, T0, T0 + 120)
    out = fc.forecasts()[1]
    # T = 2120: окно (2720, 3020], первая остановка с t_plan > 2720 — k = 13 (t_plan 2780)
    assert out["status"] == "ok" and out["T"] == T0 + 120
    assert out["target_stop_id"] == "trA-13" and out["target_plan"] == T0 + 60 * 13
    assert out["target_stop"] == "Остановка 13"
    assert out["delay_s"] == 42.0 and out["p_late"] == pytest.approx(0.3)
    assert out["reasons"] == ["причина"]


def test_stream_clock_is_the_newest_fix_of_any_unit(monkeypatch) -> None:
    fc = make(monkeypatch)
    feed(fc, 1, T0, T0 + 100)
    feed(fc, 2, T0, T0 + 400)                       # другая машина ушла вперед по времени
    out = fc.forecasts()
    assert out[1]["T"] == out[2]["T"] == T0 + 400   # у молчащей машины окно едет вместе с часами
    assert out[1]["last_ping"] == T0 + 100


def test_statuses_for_short_history_end_of_plan_and_silence(monkeypatch) -> None:
    fc = make(monkeypatch)
    fc.ingest(fix(1, T0))
    assert fc.forecasts()[1]["status"] == "few_pings"

    feed(fc, 2, T0 + 60 * 39 - 60, T0 + 60 * 39)    # конец расписания: через 10–15 мин остановок нет
    assert fc.forecasts()[2]["status"] == "no_target"

    fc.ingest(fix(2, T0 + 60 * 39 + STALE_S + 60))  # unit 2 ушел вперед по часам, unit 1 молчит давно
    assert fc.forecasts()[1]["status"] == "no_signal"


def test_recompute_budget_spreads_work_over_calls(monkeypatch) -> None:
    fc = make(monkeypatch, max_recompute=1)
    feed(fc, 1, T0, T0 + 100)
    feed(fc, 2, T0, T0 + 100)
    assert len(fc.forecasts()) == 1
    assert len(fc.forecasts()) == 2


def test_speed_shown_to_the_dispatcher_is_finite_even_if_the_last_fix_is_invalid(monkeypatch) -> None:
    fc = make(monkeypatch)
    feed(fc, 1, T0, T0 + 100)
    fc.ingest(fix(1, T0 + 110, lat=0.0, valid=False, speed=0))   # скорость такой отметки неизвестна (NaN внутри)
    speed = fc.forecasts()[1]["speed"]
    assert np.isfinite(speed) and speed == 20.0                  # последняя известная


def test_invalid_fixes_do_not_count_as_positions(monkeypatch) -> None:
    fc = make(monkeypatch)
    for t in range(T0, T0 + 100, 10):
        fc.ingest(fix(1, t, lat=0.0, valid=False, speed=0))
    assert fc.forecasts()[1]["status"] == "few_pings"
