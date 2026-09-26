"""Модели для живого потока NDTP: те же 24 признака, но cur_dev_s — наша оценка (ml_service/cur_dev.py).

В потоке NDTP подсказки cur_dev_s нет, поэтому модель должна учиться на оценках нашего кода:
проверка на test показала, что так просадка MAE меньше (+7.7 с против +14.1 с у модели, обученной
на подсказке организаторов; scripts/check_service.py). Как у v2: число деревьев — GroupKFold(5) по tr_id
на train, финальные модели учатся на train + test.
Сохраняет models/hackathon_v2_online.cbm и models/hackathon_v2_online_classifier.cbm (v2 не трогает).
Запуск из корня проекта: python scripts/model_online.py"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_service.cur_dev import estimate_cur_dev_detail
from ml_service.features import DATA, full_features, load_plan, load_points, load_traffic
from ml_service.models import (CLF_PARAMS, ONLINE_CLASSIFIER_PATH, ONLINE_REGRESSOR_PATH, REG_PARAMS,
                               fit_classifier, fit_regressor, mae)


def load(name):
    pts = load_points(DATA / "labels" / f"labels_{name}.csv")
    traffic, plan = load_traffic(DATA / name / "traffic.csv"), load_plan(DATA / name / "schedule.csv")
    X = full_features(pts, traffic, plan)
    X["cur_dev_s"] = estimate_cur_dev_detail(pts, traffic, plan)["cur_dev_est"].to_numpy()
    return pts, X


tr, Xtr = load("train")
te, Xte = load("test")
ytr, yte = tr["target_delay_s"].to_numpy(float), te["target_delay_s"].to_numpy(float)
ctr, cte = tr["target_class"].to_numpy(), te["target_class"].to_numpy()

reg, n_reg = fit_regressor(Xtr, ytr, tr["tr_id"])
clf, n_clf = fit_classifier(Xtr, ctr, tr["tr_id"])
print(f"обучено на train: регрессор {n_reg} деревьев, классификатор {n_clf}")
print(f"MAE на test (наш cur_dev_s на входе): {mae(yte, reg.predict(Xte)):.2f} с")

X, y, c = pd.concat([Xtr, Xte], ignore_index=True), np.concatenate([ytr, yte]), np.concatenate([ctr, cte])
CatBoostRegressor(iterations=n_reg, **REG_PARAMS).fit(X, y).save_model(str(ONLINE_REGRESSOR_PATH))
CatBoostClassifier(iterations=n_clf, **CLF_PARAMS).fit(X, c).save_model(str(ONLINE_CLASSIFIER_PATH))
print("сохранено:", ONLINE_REGRESSOR_PATH.name, ONLINE_CLASSIFIER_PATH.name)
