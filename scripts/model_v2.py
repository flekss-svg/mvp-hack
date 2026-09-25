"""Задача 3: CatBoost v2 = признаки v1 + телеметрия. Сравнение с v1 и файл сдачи.
Запуск из корня проекта: python scripts/model_v2.py"""
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.model_selection import GroupKFold

from telemetry_features import build, load_plan, load_traffic, to_ts

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "hackathon"
OUT = ROOT / "submissions"
OUT.mkdir(exist_ok=True)
PARAMS = dict(loss_function="MAE", depth=4, learning_rate=0.03, l2_leaf_reg=10, random_seed=42, verbose=0)


def mae(y, p):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def load_points(path):
    df = pd.read_csv(path, dtype={"sample_id": str, "tr_id": str, "target_stop_id": str})
    df["T_s"] = to_ts(df["T"])
    df["tgt_s"] = to_ts(df["target_time_begin"])
    return df


def base_features(df):
    X = pd.DataFrame(index=df.index)
    X["cur_dev_s"] = df["cur_dev_s"]
    X["horizon_s"] = df["tgt_s"] - df["T_s"]
    X["tgt_min_of_day"] = (df["tgt_s"] % 86400) / 60
    return X


def full_features(pts, part, plan_file):
    print(f"  {part}: телеметрия...", flush=True)
    tel = build(pts, load_traffic(D / part / "traffic.csv"), load_plan(D / part / plan_file))
    return pd.concat([base_features(pts), tel], axis=1)


def fit_cv(X, y, groups):
    best = []
    for a, b in GroupKFold(5).split(X, y, groups):
        m = CatBoostRegressor(iterations=3000, od_type="Iter", od_wait=150, **PARAMS)
        m.fit(X.iloc[a], y[a], eval_set=(X.iloc[b], y[b]))
        best.append(m.get_best_iteration() + 1)
    n = int(np.median(best))
    return CatBoostRegressor(iterations=n, **PARAMS).fit(X, y), n


tr = load_points(D / "labels" / "labels_train.csv")
te = load_points(D / "labels" / "labels_test.csv")
va = load_points(D / "validate" / "points.csv")

print("Считаю признаки:")
Xtr = full_features(tr, "train", "schedule.csv")
Xte = full_features(te, "test", "schedule.csv")
Xva = full_features(va, "validate", "schedule_plan.csv")
Xte, Xva = Xte.reindex(columns=Xtr.columns), Xva.reindex(columns=Xtr.columns)

print("\n=== Заполненность ключевых признаков (доля не пустых) ===")
for c in ["dist_straight_m", "dist_route_m", "n_stops_ahead", "eff_speed_600", "phys_delay_600"]:
    if c in Xtr:
        print(f"  {c:18s} train {Xtr[c].notna().mean():5.0%}  test {Xte[c].notna().mean():5.0%}  "
              f"validate {Xva[c].notna().mean():5.0%}")

ytr, yte = tr["target_delay_s"].to_numpy(float), te["target_delay_s"].to_numpy(float)
base_cols = list(base_features(tr).columns)

m1, n1 = fit_cv(Xtr[base_cols], ytr, tr["tr_id"])
m2, n2 = fit_cv(Xtr, ytr, tr["tr_id"])
print("\n=== Качество на TEST ===")
print(f"  cur_dev_s (baseline)          {mae(yte, te['cur_dev_s']):7.2f}")
print(f"  v1: 3 признака, {n1:4d} деревьев  {mae(yte, m1.predict(Xte[base_cols])):7.2f}")
print(f"  v2: {Xtr.shape[1]:2d} признаков, {n2:4d} деревьев {mae(yte, m2.predict(Xte)):7.2f}")

if "phys_delay_600" in Xte:
    ok = Xte["phys_delay_600"].notna()
    print(f"  (сам по себе phys_delay_600 как прогноз: {mae(yte[ok], Xte.loc[ok, 'phys_delay_600']):.2f} "
          f"на {ok.mean():.0%} точек)")

print("\n=== Важность признаков v2 (топ-12) ===")
imp = pd.Series(m2.get_feature_importance(), index=Xtr.columns).sort_values(ascending=False)
for k, v in imp.head(12).items():
    print(f"  {k:20s} {v:6.1f}")

# сдача: обучение на train + test
Xall = pd.concat([Xtr, Xte], ignore_index=True)
yall = np.concatenate([ytr, yte])
final = CatBoostRegressor(iterations=n2, **PARAMS).fit(Xall, yall)
sub = pd.read_csv(D / "sample_submission.csv", sep=";", dtype={"sample_id": str})
sub["prediction"] = sub["sample_id"].map(dict(zip(va["sample_id"], final.predict(Xva)))).round(1)
assert sub["prediction"].notna().all()
path = OUT / "submission_v2_catboost_telemetry.csv"
sub.to_csv(path, sep=";", index=False, encoding="utf-8")
print(f"\nФайл сдачи: {path.relative_to(ROOT)}")

final.save_model(str(ROOT / "models" / "hackathon_v2_catboost.cbm"))
pd.Series(list(Xtr.columns)).to_csv(ROOT / "models" / "hackathon_v2_features.csv", index=False)
print("Модель сохранена: models/hackathon_v2_catboost.cbm")