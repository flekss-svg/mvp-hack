"""Оценка качества модели: метрики и уровни риска для диспетчерского дашборда.

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
