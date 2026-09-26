"""Задача 5.4: устойчивость к другим дням — «обстановка в городе» вместо tgt_min_of_day.

Сравнение на test (модели обучены только на train, число деревьев — GroupKFold(5) по tr_id):
  v2      — 24 признака как есть (tgt_min_of_day внутри);
  v2 -tod — без tgt_min_of_day (проверка, сколько он дает);
  v3      — без tgt_min_of_day + city_speed_mean_600 + city_stopped_share_600.
Финальная v3 (train + test) сохраняется под новым именем, v2 не трогаем.
Запуск из корня проекта: python scripts/model_city.py"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_service.features import DATA, MODELS, city_features, full_features, load_plan, load_points, load_traffic
from ml_service.models import REG_PARAMS, fit_regressor, mae

NEW_MODEL, NEW_FEATURES = MODELS / "hackathon_v3_city.cbm", MODELS / "hackathon_v3_city_features.csv"


def load(name):
    pts = load_points(DATA / "labels" / f"labels_{name}.csv")
    traffic = load_traffic(DATA / name / "traffic.csv")
    X = full_features(pts, traffic, load_plan(DATA / name / "schedule.csv"))
    return pts, pd.concat([X, city_features(pts, traffic)], axis=1)


tr_pts, Xtr = load("train")
te_pts, Xte = load("test")
ytr, yte = tr_pts["target_delay_s"].to_numpy(float), te_pts["target_delay_s"].to_numpy(float)
city = [c for c in Xtr.columns if c.startswith("city_")]
sets = {
    "v2 (с tgt_min_of_day)": [c for c in Xtr.columns if c not in city],
    "v2 без tgt_min_of_day": [c for c in Xtr.columns if c not in city and c != "tgt_min_of_day"],
    "v3 (город вместо времени суток)": [c for c in Xtr.columns if c != "tgt_min_of_day"],
}

print(f"baseline cur_dev_s: {mae(yte, te_pts['cur_dev_s']):.2f} с;  ноль: {mae(yte, np.zeros(len(yte))):.2f} с\n")
res = {}
for name, cols in sets.items():
    model, n = fit_regressor(Xtr[cols], ytr, tr_pts["tr_id"])
    res[name] = mae(yte, model.predict(Xte[cols]))
    print(f"{name:34s} {len(cols):2d} признаков, {n:4d} деревьев: MAE test {res[name]:6.2f} с", flush=True)
    if name.startswith("v3"):
        imp = pd.Series(model.get_feature_importance(), index=cols).sort_values(ascending=False)
        print("  важность v3 (топ-10):", ", ".join(f"{k} {v:.1f}" for k, v in imp.head(10).items()))
        print("  город:", ", ".join(f"{c} {imp[c]:.1f}" for c in city))

d = res["v3 (город вместо времени суток)"] - res["v2 (с tgt_min_of_day)"]
print(f"\nv3 против v2: {d:+.2f} с -> {'не хуже чем на 3 с: v3 предпочтительна для защиты' if d <= 3 else 'хуже больше чем на 3 с: остаёмся на v2'}")

cols = sets["v3 (город вместо времени суток)"]
n = fit_regressor(Xtr[cols], ytr, tr_pts["tr_id"])[1]
final = CatBoostRegressor(iterations=n, **REG_PARAMS).fit(pd.concat([Xtr[cols], Xte[cols]], ignore_index=True),
                                                          np.concatenate([ytr, yte]))
final.save_model(str(NEW_MODEL))
pd.Series(cols).to_csv(NEW_FEATURES, index=False)
print(f"Сохранено: {NEW_MODEL.name}, {NEW_FEATURES.name}")
