import numpy as np
import pytest

from app.model.evaluation import baselines, mae, mae_by_bucket, mae_report, risk_levels


pytestmark = pytest.mark.unit


def test_mae_and_report() -> None:
    assert mae([0, 2, 4], [1, 2, 2]) == pytest.approx(1.0)
    assert mae_report([0, 2], {"model": [1, 2]}, "all") == {
        "выборка": "all",
        "n": 2,
        "model": 0.5,
    }


def test_baselines_have_expected_values() -> None:
    result = baselines([1, 2], median_delay=3.0, n=2)
    np.testing.assert_array_equal(result["как сейчас (опоздание сохранится)"], [1, 2])
    np.testing.assert_array_equal(result["по расписанию (0 мин)"], [0, 0])
    np.testing.assert_array_equal(result["константа (медиана обучения)"], [3, 3])


def test_risk_levels_and_empty_buckets() -> None:
    levels = risk_levels(np.array([0, 1, 1]), np.array([0.1, 0.4, 0.9]))
    assert levels["низкий (<0.3)"]["share"] == pytest.approx(1 / 3, abs=1e-4)
    rows = mae_by_bucket([1, 12], {"model": [2, 10]})
    assert [row["диапазон"] for row in rows] == ["нет опоздания", "больше 10 мин"]
