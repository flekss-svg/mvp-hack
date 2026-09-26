import numpy as np
import pytest

from app.engine.feature_definitions import FEATURES
from app.model.explain import REASONS, main_reasons, reason_text

pytestmark = pytest.mark.unit


def shap(**contrib: float) -> np.ndarray:
    row = np.zeros(len(FEATURES))
    for feature, value in contrib.items():
        row[FEATURES.index(feature)] = value
    return row[None, :]


def names(indices) -> list:
    return [REASONS[i] for i in indices if i >= 0]


def test_features_of_one_cause_are_summed() -> None:
    # по отдельности каждый признак замедления меньше delay_now, вместе — больше
    (r,) = main_reasons(shap(delay_now=1.0, ahead_recent_sum=0.6, ahead_recent_max=0.6))
    assert names(r) == ["Замедление на участке впереди (по другим машинам)", "Машина уже отстаёт от графика"]


def test_service_features_are_never_a_cause() -> None:
    (r,) = main_reasons(shap(progress=5.0, stops_left=3.0, lead_headway_dev=0.4))
    assert names(r) == ["Сбился интервал с впереди идущей машиной"]


def test_weak_second_reason_and_negative_contributions_are_dropped() -> None:
    (r,) = main_reasons(shap(delay_now=2.0, rain=0.1, lead_delay=-3.0))
    assert names(r) == ["Машина уже отстаёт от графика"]
    (r,) = main_reasons(shap(delay_now=-1.0))
    assert names(r) == []


def test_reason_text() -> None:
    first, second = REASONS.index("Машина уже отстаёт от графика"), REASONS.index("Дождь")
    assert reason_text([first, second]) == "Машина уже отстаёт от графика; дождь"
    assert reason_text([-1, -1]) is None
    assert main_reasons(np.empty((0, len(FEATURES)))).shape == (0, 2)
