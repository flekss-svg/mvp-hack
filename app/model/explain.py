"""Почему модель считает, что машина опоздает: главные причины конкретного прогноза.

Вклад признаков — SHAP-значения CatBoost (DelayPredictor.explain): разложение именно этого
прогноза, а не общая важность признаков по модели. Вклады признаков, описывающих одну
причину, складываются; служебные признаки причиной не считаются (FEATURE_REASONS).

Берем две причины: чаще всего главный вклад — «уже отстает», и одна эта фраза не
объясняет, что еще толкает машину к опозданию. Вторая показывается, только если ее вклад
заметен на фоне первой.
"""
import numpy as np

from app.engine.feature_definitions import FEATURE_REASONS, FEATURES

REASONS = sorted(set(FEATURE_REASONS.values()))
TOP = 2
SECONDARY_SHARE = 0.2   # вторая причина — если ее вклад не меньше этой доли от первой

# признак -> причина: умножение вкладов на эту матрицу суммирует их по причинам
_BY_REASON = np.zeros((len(FEATURES), len(REASONS)))
for _i, _f in enumerate(FEATURES):
    if _f in FEATURE_REASONS:
        _BY_REASON[_i, REASONS.index(FEATURE_REASONS[_f])] = 1.0


def main_reasons(shap: np.ndarray) -> np.ndarray:
    """shap: (n, len(FEATURES)) — вклад признаков в прогноз «опоздает».
    Возвращает (n, TOP) индексов в REASONS по убыванию вклада; -1 — причины нет."""
    by_reason = np.asarray(shap) @ _BY_REASON
    out = np.full((len(by_reason), TOP), -1, dtype=np.int16)
    if not len(by_reason):
        return out
    order = np.argsort(-by_reason, axis=1)[:, :TOP]
    value = np.take_along_axis(by_reason, order, axis=1)
    keep = value > 0
    keep[:, 1:] &= value[:, 1:] >= SECONDARY_SHARE * value[:, :1]
    out[keep] = order[keep]
    return out


def reason_text(indices, reasons: list[str] = REASONS) -> str | None:
    """Индексы причин -> одна фраза для диспетчера: «Первая; вторая»."""
    parts = [reasons[i] for i in indices if i >= 0]
    if not parts:
        return None
    return "; ".join([parts[0], *(p[0].lower() + p[1:] for p in parts[1:])])
