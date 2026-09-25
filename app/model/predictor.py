"""Обёртка над ML-моделью предиктора задержек.

Изолирует остальной код (service/, replay_build.py, model/training.py) от конкретной
библиотеки — сейчас CatBoost. Если завтра модель поменяется (другой градиентный бустинг,
нейросеть), меняется только этот файл: у DelayPredictor остается тот же интерфейс
(load/save/fit/predict_risk/feature_importance).

Моделей две, с одинаковыми признаками:
  * DelayPredictor — вероятность опоздания (уровни риска для диспетчера);
  * DelayRegressor — само отклонение в минутах через 10–15 минут. Организаторы оценивают
    решение по MAE, поэтому эта модель обучается прямо под MAE: функция потерь совпадает
    с метрикой оценки.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor

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


class DelayRegressor:
    """Отклонение от графика в минутах через 10–15 минут. Обучается под MAE."""

    def __init__(self, model: CatBoostRegressor | None = None):
        self._model = model or CatBoostRegressor()

    @classmethod
    def new(cls, **hyperparams) -> "DelayRegressor":
        hyperparams.setdefault("loss_function", "MAE")
        hyperparams.setdefault("eval_metric", "MAE")
        return cls(CatBoostRegressor(**hyperparams))

    @classmethod
    def load(cls, path: Path) -> "DelayRegressor":
        model = CatBoostRegressor()
        model.load_model(str(path))
        return cls(model)

    def save(self, path: Path) -> None:
        self._model.save_model(str(path))

    def fit(self, X: pd.DataFrame, y, eval_set=None) -> "DelayRegressor":
        self._model.fit(X[FEATURES], y, eval_set=eval_set)
        return self

    def predict_delay(self, features) -> np.ndarray:
        """features: DataFrame с колонками FEATURES -> отклонение в минутах."""
        if isinstance(features, pd.DataFrame):
            features = features[FEATURES]
        return self._model.predict(features)

    def feature_importance(self) -> pd.Series:
        return pd.Series(self._model.get_feature_importance(), index=FEATURES).sort_values(ascending=False)
