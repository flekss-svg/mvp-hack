"""Задача 5.3: проверка онлайн-оценки cur_dev_s (ml_service/cur_dev.py).

Критерии ТЗ:
  1. оценка есть для >= 90% точек;
  2. медианная ошибка против cur_dev_s организаторов <= 30 с;
  3. MAE модели с нашим cur_dev_s хуже, чем с cur_dev_s организаторов, не более чем на 10 с.
     Считаем два варианта, потому что ТЗ допускает обе трактовки:
       А) модель обучена на cur_dev_s организаторов, на вход подан наш (худший случай);
       Б) модель обучена на наших оценках и на них же работает (так она будет жить в сервисе).

Запуск из корня проекта:
  python scripts/check_service.py test    # модель обучена на train, проверка на test
  python scripts/check_service.py train   # прогноз по фолдам GroupKFold(5) внутри train
Модель — регрессор с гиперпараметрами v2. Точки без оценки идут в модель как NaN (так она увидит их в сервисе)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_service.cur_dev import estimate_cur_dev_detail
from ml_service.features import DATA, full_features, load_plan, load_points, load_traffic
from ml_service.models import REG_PARAMS, cv_iterations, mae

part = sys.argv[1] if len(sys.argv) > 1 else "test"
assert part in ("train", "test"), "аргумент: train или test"


def load(name):
    pts = load_points(DATA / "labels" / f"labels_{name}.csv")
    traffic, plan = load_traffic(DATA / name / "traffic.csv"), load_plan(DATA / name / "schedule.csv")
    return pts, traffic, plan, full_features(pts, traffic, plan)


pts, traffic, plan, X = load(part)
y = pts["target_delay_s"].to_numpy(float)
det = estimate_cur_dev_detail(pts, traffic, plan)
est, truth = det["cur_dev_est"].to_numpy(), pts["cur_dev_s"].to_numpy(float)
ok = np.isfinite(est)
err = est[ok] - truth[ok]

print(f"=== {part}: {len(pts)} точек ===")
cover, med = ok.mean(), float(np.median(np.abs(err)))
print(f"1. покрытие оценкой: {cover:.1%}                      (нужно >= 90%)  {'OK' if cover >= 0.9 else 'НЕТ'}")
print(f"2. медианная |ошибка|: {med:.1f} с (MAE {np.mean(np.abs(err)):.1f} с, смещение {np.median(err):+.1f} с)"
      f"   (нужно <= 30 с)  {'OK' if med <= 30 else 'НЕТ'}")
for s in ["arrival", "eta", "passed"]:
    m = (det["source"] == s).to_numpy() & ok
    if m.any():
        e = est[m] - truth[m]
        print(f"     источник {s:8s} {m.sum():5d} точек ({m.sum() / len(pts):.0%}): "
              f"медиана {np.median(np.abs(e)):5.1f} с, MAE {np.mean(np.abs(e)):6.1f} с")

# критерий 3
def with_cur_dev(X_, col):
    X_ = X_.copy()
    X_["cur_dev_s"] = col
    return X_


def new_regressor(X_, y_, groups_):
    n_ = cv_iterations(lambda **kw: CatBoostRegressor(**REG_PARAMS, **kw), X_, y_, groups_)
    return n_


X_ours = with_cur_dev(X, est)
if part == "test":
    trp, trt, trplan, Xtr = load("train")
    ytr, gtr = trp["target_delay_s"].to_numpy(float), trp["tr_id"]
    Xtr_ours = with_cur_dev(Xtr, estimate_cur_dev_detail(trp, trt, trplan)["cur_dev_est"].to_numpy())
    mA = CatBoostRegressor(iterations=new_regressor(Xtr, ytr, gtr), **REG_PARAMS).fit(Xtr, ytr)
    mB = CatBoostRegressor(iterations=new_regressor(Xtr_ours, ytr, gtr), **REG_PARAMS).fit(Xtr_ours, ytr)
    p_org, p_A, p_B = mA.predict(X), mA.predict(X_ours), mB.predict(X_ours)
else:
    nA, nB = new_regressor(X, y, pts["tr_id"]), new_regressor(X_ours, y, pts["tr_id"])
    p_org, p_A, p_B = np.zeros(len(y)), np.zeros(len(y)), np.zeros(len(y))
    for a, b in GroupKFold(5).split(X, y, pts["tr_id"]):
        mA = CatBoostRegressor(iterations=nA, **REG_PARAMS).fit(X.iloc[a], y[a])
        mB = CatBoostRegressor(iterations=nB, **REG_PARAMS).fit(X_ours.iloc[a], y[a])
        p_org[b], p_A[b], p_B[b] = mA.predict(X.iloc[b]), mA.predict(X_ours.iloc[b]), mB.predict(X_ours.iloc[b])
m_org, m_A, m_B = mae(y, p_org), mae(y, p_A), mae(y, p_B)
print(f"3. MAE модели с cur_dev организаторов: {m_org:.1f} с")
print(f"   А) обучена на организаторском, подан наш:  {m_A:.1f} с  ({m_A - m_org:+.1f} с)  "
      f"{'OK' if m_A - m_org <= 10 else 'НЕТ'}   (нужно <= +10 с)")
print(f"   Б) обучена на наших оценках, подан наш:    {m_B:.1f} с  ({m_B - m_org:+.1f} с)  "
      f"{'OK' if m_B - m_org <= 10 else 'НЕТ'}   (нужно <= +10 с)")
print(f"   (справка: cur_dev_s организаторов как прогноз {mae(y, truth):.1f} с; "
      f"наша оценка как прогноз {mae(y[ok], est[ok]):.1f} с на {cover:.0%} точек)")
