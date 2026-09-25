"""Оценка качества модели: MAE (основная метрика оценки решения), метрики классификации
и уровни риска для диспетчерского дашборда.

Отделено от model/training.py, чтобы можно было пересчитать метрики (например, на новом
тестовом периоде) не трогая код обучения.
"""
import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score


def metrics(y, score, name: str) -> dict:
    p, r, thr = precision_recall_curve(y, score)
    # точность при полноте 70% — «сколько тревог окажутся настоящими, если ловим 70% задержек»
    i = np.where(r >= 0.7)[0][-1]
    return {"model": name, "roc_auc": round(roc_auc_score(y, score), 4),
            "pr_auc": round(average_precision_score(y, score), 4),
            "precision_at_recall70": round(float(p[i]), 4), "base_rate": round(float(y.mean()), 4)}


def risk_levels(y, score, bounds=(0.3, 0.6)) -> dict:
    """Насколько точны тревоги каждого уровня риска — то, что видит диспетчер."""
    lv = np.digitize(score, list(bounds))
    names = [f"низкий (<{bounds[0]})", f"средний ({bounds[0]}–{bounds[1]})", f"высокий (≥{bounds[1]})"]
    return {name: {"share": round(float((lv == i).mean()), 4),
                   "actual_late_rate": round(float(y[lv == i].mean()), 4)}
            for i, name in enumerate(names)}


# ---------- регрессия: MAE, основная метрика оценки ----------

def mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(np.asarray(y_true, float) - np.asarray(y_pred, float))))


def mae_report(y_true, predictions: dict, label: str) -> dict:
    """MAE модели и базовых правил на одной выборке. predictions: имя -> прогноз в минутах."""
    y_true = np.asarray(y_true, float)
    out = {"выборка": label, "n": int(len(y_true))}
    out.update({name: round(mae(y_true, p), 3) for name, p in predictions.items()})
    return out


def baselines(delay_now, median_delay: float, n: int) -> dict:
    """Простые правила, с которыми сравниваем модель."""
    return {"как сейчас (опоздание сохранится)": np.asarray(delay_now, float),
            "по расписанию (0 мин)": np.zeros(n),
            "константа (медиана обучения)": np.full(n, median_delay)}


def mae_by_bucket(y_true, predictions: dict, buckets=((-1e9, 3, "нет опоздания"),
                                                      (3, 10, "3–10 мин"),
                                                      (10, 1e9, "больше 10 мин"))) -> list:
    """Разбивка ошибки по величине фактического опоздания — видно, где модель слабее."""
    y_true = np.asarray(y_true, float)
    rows = []
    for lo, hi, name in buckets:
        m = (y_true >= lo) & (y_true < hi)
        if not m.any():
            continue
        row = {"диапазон": name, "n": int(m.sum())}
        row.update({k: round(mae(y_true[m], np.asarray(v, float)[m]), 3) for k, v in predictions.items()})
        rows.append(row)
    return rows
