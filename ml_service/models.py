"""Модели: регрессор (как в v2) и классификатор вероятностей early / ontime / late.

Гиперпараметры регрессора те же, что в scripts/model_v2.py (v2 не менять). Число деревьев
выбирается по GroupKFold(5) по tr_id внутри обучающей выборки: медиана точек ранней остановки.
"""
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.model_selection import GroupKFold

from .features import CLASSES, MODELS

REG_PARAMS = dict(loss_function="MAE", depth=4, learning_rate=0.03, l2_leaf_reg=10, random_seed=42, verbose=0)
CLF_PARAMS = dict(loss_function="MultiClass", depth=4, learning_rate=0.03, l2_leaf_reg=10, random_seed=42, verbose=0)

CLASSIFIER_PATH = MODELS / "hackathon_v2_classifier.cbm"
REGRESSOR_PATH = MODELS / "hackathon_v2_catboost.cbm"
# Для живого потока: обучены на cur_dev_s, который оценивает наш код (ml_service/cur_dev.py), а не на
# подсказке организаторов — в потоке NDTP подсказки нет.
ONLINE_REGRESSOR_PATH = MODELS / "hackathon_v2_online.cbm"
ONLINE_CLASSIFIER_PATH = MODELS / "hackathon_v2_online_classifier.cbm"


def mae(y, p) -> float:
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def cv_iterations(make_model, X, y, groups, max_iter=3000, wait=150) -> int:
    """Медиана лучшей итерации по GroupKFold(5) по tr_id (только внутри переданной выборки)."""
    best = []
    for a, b in GroupKFold(5).split(X, y, groups):
        m = make_model(iterations=max_iter, od_type="Iter", od_wait=wait)
        m.fit(X.iloc[a], y[a], eval_set=(X.iloc[b], y[b]))
        best.append(m.get_best_iteration() + 1)
    return int(np.median(best))


def fit_regressor(X, y, groups):
    n = cv_iterations(lambda **kw: CatBoostRegressor(**REG_PARAMS, **kw), X, y, groups)
    return CatBoostRegressor(iterations=n, **REG_PARAMS).fit(X, y), n


def fit_classifier(X, y_class, groups):
    """y_class — строки 'early' / 'ontime' / 'late'."""
    y = np.asarray(y_class)
    # на CV logloss падает и после 3000 итераций (шаг 0.03), поэтому потолок выше, чем у регрессора
    n = cv_iterations(lambda **kw: CatBoostClassifier(**CLF_PARAMS, **kw), X, y, groups, max_iter=8000)
    return CatBoostClassifier(iterations=n, **CLF_PARAMS).fit(X, y), n


def load_classifier(path=CLASSIFIER_PATH) -> CatBoostClassifier:
    return CatBoostClassifier().load_model(str(path))


def predict_class_probs(X: pd.DataFrame, model: CatBoostClassifier = None) -> pd.DataFrame:
    """Вероятности классов: DataFrame со столбцами early, ontime, late (строки сходятся с X)."""
    model = model or load_classifier()
    proba = model.predict_proba(X[model.feature_names_] if model.feature_names_ else X)
    out = pd.DataFrame(proba, columns=[str(c) for c in model.classes_], index=X.index)
    return out[list(CLASSES)]
