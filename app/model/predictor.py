"""Обёртка над ML-моделью предиктора задержек.

Изолирует остальной код (service/, dashboard_export.py, model/training.py) от конкретной
библиотеки — сейчас CatBoost. Если завтра модель поменяется (другой градиентный бустинг,
нейросеть), меняется только этот файл: у DelayPredictor остается тот же интерфейс
(load/save/fit/predict_risk/feature_importance).
"""
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from app.engine.feature_definitions import FEATURES


class DelayPredictor:
    def __init__(self, model: CatBoostClassifier | None = None):
        self._model = model or CatBoostClassifier()

    @classmethod
    def new(cls, **hyperparams) -> "DelayPredictor":
        """Новая, необученная модель — для model/training.py."""
        return cls(CatBoostClassifier(**hyperparams))

    @classmethod
    def load(cls, path: Path) -> "DelayPredictor":
        model = CatBoostClassifier()
        model.load_model(str(path))
        return cls(model)

    def save(self, path: Path) -> None:
        self._model.save_model(str(path))

    def fit(self, X: pd.DataFrame, y, eval_set=None) -> "DelayPredictor":
        self._model.fit(X[FEATURES], y, eval_set=eval_set)
        return self

    def predict_risk(self, features) -> np.ndarray:
        """features: DataFrame с колонками FEATURES (в любом порядке) -> вероятность опоздания."""
        if isinstance(features, pd.DataFrame):
            features = features[FEATURES]
        return self._model.predict_proba(features)[:, 1]

    def feature_importance(self) -> pd.Series:
        return pd.Series(self._model.get_feature_importance(), index=FEATURES).sort_values(ascending=False)
