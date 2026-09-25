"""Задача 2: проверка часового пояса + модель v1 на признаках точек + файлы сдачи.
Запуск из корня проекта: python scripts/model_v1.py"""
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.linear_model import QuantileRegressor
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "hackathon"
OUT = ROOT / "submissions"
OUT.mkdir(exist_ok=True)
MAE_TARGET_EST = 78.5  # оценка по test из формулы балла: cur_dev_s дает ~0.40


def to_ts(s):
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.99:
        num = num.astype("float64")
        return (num / 1000 if num.median() > 1e11 else num).round().astype("int64")
    dt = pd.to_datetime(s, format="ISO8601", utc=True)
    return ((dt - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).astype("Int64")


def mae(y, p):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def est_score(m, mae_zero):
    return max(0.0, min(1.0, (mae_zero - m) / (mae_zero - MAE_TARGET_EST)))


def load(path):
    df = pd.read_csv(path, dtype={"sample_id": str, "tr_id": str, "target_stop_id": str})
    df["T_s"] = to_ts(df["T"]).astype("int64")
    df["tgt_s"] = to_ts(df["target_time_begin"]).astype("int64")
    return df


def features(df):
    X = pd.DataFrame(index=df.index)
    X["cur_dev_s"] = df["cur_dev_s"]
    X["horizon_s"] = df["tgt_s"] - df["T_s"]
    X["tgt_min_of_day"] = (df["tgt_s"] % 86400) / 60
    return X


def tz_check(part, pts):
    """Сверяем T с телеметрией. Если часовые пояса разъехались, будет сдвиг ~3 ч."""
    sid = pd.to_numeric(pts["sample_id"].str.split("_").str[-1], errors="coerce")
    print(f"  sample_id заканчивается на T: {(sid == pts['T_s']).mean():.0%} "
          f"(медианная разница {float((sid - pts['T_s']).median()):.0f} c)")
    tr = pd.read_csv(D / part / "traffic.csv", usecols=["tr_id", "event_time"], dtype={"tr_id": str})
    tr["t"] = to_ts(tr["event_time"])
    tr = tr.dropna(subset=["t"]).astype({"t": "int64"}).sort_values("t")
    p = pts[["sample_id", "tr_id", "T_s"]].sort_values("T_s")
    back = pd.merge_asof(p, tr[["tr_id", "t"]], left_on="T_s", right_on="t", by="tr_id", direction="backward")
    fwd = pd.merge_asof(p, tr[["tr_id", "t"]], left_on="T_s", right_on="t", by="tr_id", direction="forward")
    lag, lead = back["T_s"] - back["t"], fwd["t"] - fwd["T_s"]
    print(f"  последняя отметка до T: есть у {lag.notna().mean():.0%} точек, "
          f"отставание медиана {lag.median():.0f} c, 90% {lag.quantile(.9):.0f} c")
    print(f"  ближайшая отметка после T: медиана {lead.median():.0f} c")
    print(f"  телеметрия {part}: {pd.to_datetime(tr.t.min(), unit='s')} .. {pd.to_datetime(tr.t.max(), unit='s')}")


tr, te, va = (load(D / "labels" / "labels_train.csv"), load(D / "labels" / "labels_test.csv"),
              load(D / "validate" / "points.csv"))

print("=== Проверка часового пояса ===")
for part, pts in [("train", tr), ("test", te), ("validate", va)]:
    print(part)
    tz_check(part, pts)

ytr, yte = tr["target_delay_s"].to_numpy(float), te["target_delay_s"].to_numpy(float)
mz = mae(yte, 0)
rows = []


def report(name, p):
    m = mae(yte, p)
    rows.append((name, m, est_score(m, mz)))


report("ноль", np.zeros(len(yte)))
report("cur_dev_s (baseline)", te["cur_dev_s"])

# A. Линейная поправка: prediction = a * cur_dev_s + b, подобрана под MAE (медианная регрессия)
qr = QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs").fit(tr[["cur_dev_s"]], ytr)
report(f"A: {qr.coef_[0]:.2f}*cur_dev_s + {qr.intercept_:.1f}", qr.predict(te[["cur_dev_s"]]))

# B. CatBoost под MAE. Число деревьев подбираем кросс-валидацией ПО МАШИНАМ внутри train
Xtr, Xte, Xva = features(tr), features(te), features(va)
params = dict(loss_function="MAE", depth=4, learning_rate=0.03, l2_leaf_reg=10, random_seed=42, verbose=0)
best = []
for a, b in GroupKFold(5).split(Xtr, ytr, tr["tr_id"]):
    m = CatBoostRegressor(iterations=2000, od_type="Iter", od_wait=100, **params)
    m.fit(Xtr.iloc[a], ytr[a], eval_set=(Xtr.iloc[b], ytr[b]))
    best.append(m.get_best_iteration() + 1)
n_it = int(np.median(best))
cb = CatBoostRegressor(iterations=n_it, **params).fit(Xtr, ytr)
report(f"B: CatBoost v1, {n_it} деревьев", cb.predict(Xte))

print("\n=== Качество на TEST ===")
print(f"{'модель':40s} {'MAE, c':>8s} {'балл (оценка)':>14s}")
for n, m, s in rows:
    print(f"{n:40s} {m:8.2f} {s:14.2f}")

# Файлы сдачи: финальная модель обучается на train + test
allp = pd.concat([tr, te], ignore_index=True)
yall = allp["target_delay_s"].to_numpy(float)
preds = {
    "A_linear": QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs")
    .fit(allp[["cur_dev_s"]], yall).predict(va[["cur_dev_s"]]),
    "B_catboost": CatBoostRegressor(iterations=n_it, **params).fit(features(allp), yall).predict(Xva),
}
sub0 = pd.read_csv(D / "sample_submission.csv", sep=";", dtype={"sample_id": str})
print("\n=== Файлы сдачи ===")
for name, p in preds.items():
    sub = sub0.copy()
    sub["prediction"] = sub["sample_id"].map(dict(zip(va["sample_id"], p))).round(1)
    assert sub["prediction"].notna().all(), "не для всех sample_id есть прогноз"
    path = OUT / f"submission_v1_{name}.csv"
    sub.to_csv(path, sep=";", index=False, encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}")