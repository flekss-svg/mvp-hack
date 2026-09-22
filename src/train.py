"""Обучение предиктора задержек и честная оценка против простого базового правила.

Разбиение по времени (никакой перемешки дней):
  дни 1–7   — «профильные»: считаем типичное время хода по перегонам и часам
  дни 8–21  — обучение
  дни 22–28 — тест
"""
import glob
import json
import pickle
import random

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve

from config import PROC, MODELS, REPORTS, LATE_THRESHOLD_MIN, RANDOM_SEED, HOLIDAYS
from features import FEATURES, StreamState, build_hist_profile, load_schedule_index, run_day


def day_context(date, meta_row):
    d = pd.Timestamp(date)
    r, r0, r1 = meta_row["rain"], meta_row["rain_from"], meta_row["rain_to"]
    return dict(dow=d.dayofweek, weekend=int(d.dayofweek >= 5),
                holiday=int(date in HOLIDAYS),
                rain=(lambda t: r if r0 <= t <= r1 else 0.0) if r else 0.0)


def make_state(schedule, hist, route_mode, date, meta):
    s = StreamState(schedule, hist, route_mode)
    s.set_context(**day_context(date, meta.loc[date]))
    return s


def collect(files, schedule, hist, route_mode, meta, sample, rng):
    Xs, Ms = [], []
    for f in files:
        date = f.split("day=")[1][:10]
        df = pd.read_parquet(f)
        X, M = run_day(make_state(schedule, hist, route_mode, date, meta), df, sample, rng)
        M["date"] = date
        Xs.append(X)
        Ms.append(M)
        print(f"  {date}: {len(X):>8,} примеров, доля опозданий через 12 мин: {M.y.mean():.2f}")
    return pd.concat(Xs, ignore_index=True), pd.concat(Ms, ignore_index=True)


def metrics(y, score, name):
    p, r, thr = precision_recall_curve(y, score)
    # точность при полноте 70% — «сколько тревог окажутся настоящими, если ловим 70% задержек»
    i = np.where(r >= 0.7)[0][-1]
    return {"model": name, "roc_auc": round(roc_auc_score(y, score), 4),
            "pr_auc": round(average_precision_score(y, score), 4),
            "precision_at_recall70": round(float(p[i]), 4), "base_rate": round(float(y.mean()), 4)}


def main():
    rng = random.Random(RANDOM_SEED)
    files = sorted(glob.glob(str(PROC / "fact" / "day=*.parquet")))
    meta = pd.read_parquet(PROC / "sim_meta.parquet").set_index("date")
    routes = pd.read_parquet(PROC / "routes.parquet")
    route_mode = dict(zip(routes.route_id, routes["mode"]))
    schedule = load_schedule_index()

    prof, train_f, test_f = files[:7], files[7:21], files[21:]
    print("Профиль перегонов по", len(prof), "дням")
    hist = build_hist_profile([pd.read_parquet(f) for f in prof])

    print("Обучающая выборка:")
    Xtr, Mtr = collect(train_f, schedule, hist, route_mode, meta, 0.3, rng)
    print("Тестовая выборка:")
    Xte, Mte = collect(test_f, schedule, hist, route_mode, meta, 0.5, rng)

    # валидация для ранней остановки — последние 3 дня обучения
    va = Mtr["date"] >= sorted(Mtr["date"].unique())[-3]
    model = CatBoostClassifier(iterations=800, depth=8, learning_rate=0.08, loss_function="Logloss",
                               eval_metric="PRAUC", od_type="Iter", od_wait=60,
                               random_seed=RANDOM_SEED, verbose=100, thread_count=-1)
    model.fit(Xtr[~va], Mtr.y[~va], eval_set=(Xtr[va], Mtr.y[va]))

    p = model.predict_proba(Xte[FEATURES])[:, 1]
    y = Mte.y.to_numpy()
    # «ранние» случаи: сейчас машина еще НЕ опаздывает — ради них и нужна система
    early = (Xte["delay_now"] < LATE_THRESHOLD_MIN).to_numpy()

    res = {"all": [metrics(y, p, "CatBoost"),
                   metrics(y, Xte["delay_now"], "Базовое правило: текущая задержка")],
           "early_warning": [metrics(y[early], p[early], "CatBoost"),
                             metrics(y[early], Xte["delay_now"][early],
                                     "Базовое правило: текущая задержка")],
           "n_test": int(len(y)), "n_test_early": int(early.sum())}

    # уровни риска для диспетчера: насколько точны тревоги каждого уровня на тесте
    lv = np.digitize(p, [0.3, 0.6])
    res["risk_levels"] = {name: {"share": round(float((lv == i).mean()), 4),
                                 "actual_late_rate": round(float(y[lv == i].mean()), 4)}
                          for i, name in enumerate(["низкий (<0.3)", "средний (0.3–0.6)",
                                                    "высокий (≥0.6)"])}

    imp = pd.Series(model.get_feature_importance(), index=FEATURES).sort_values(ascending=False)
    res["feature_importance"] = imp.round(2).to_dict()

    MODELS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    model.save_model(str(MODELS / "delay_catboost.cbm"))
    with open(MODELS / "hist_profile.pkl", "wb") as fh:
        pickle.dump(hist, fh)
    with open(REPORTS / "metrics.json", "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
