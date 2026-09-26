"""Обучение предиктора задержек и честная оценка против простого базового правила.

Разбиение по времени (никакой перемешки дней):
  дни 1–7   — «профильные»: считаем типичное время хода по перегонам и часам
  дни 8–21  — обучение
  дни 22–28 — тест

Использует только canonical-слои: data_sources (доступ к данным), engine (признаки),
model.predictor/evaluation (обучение и оценка). Не знает деталей формата CSV data.mos.ru
и не дублирует код загрузки признаков с service/risk_service.py или replay_build.py.
"""
import json
import pickle
import random
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from app.config import HOLIDAYS, LATE_THRESHOLD_MIN, MODELS, PROC, RANDOM_SEED, REPORTS
from app.data_sources import processed_repository as repo
from app.domain.schema import DayContext
from app.engine.feature_definitions import FEATURE_DESCRIPTIONS
from app.engine.stream_state import StreamState, build_hist_profile, load_schedule_index, run_day
from app.model.evaluation import baselines, mae_by_bucket, mae_report, metrics, risk_levels
from app.model.predictor import DelayPredictor, DelayRegressor


def day_context(date, meta_row) -> DayContext:
    d = pd.Timestamp(date)
    r, r0, r1 = meta_row["rain"], meta_row["rain_from"], meta_row["rain_to"]
    return DayContext(dow=d.dayofweek, weekend=int(d.dayofweek >= 5),
                       holiday=int(date in HOLIDAYS),
                       rain=(lambda t: r if r0 <= t <= r1 else 0.0) if r else 0.0)


def make_state(schedule, hist, route_mode, date, meta) -> StreamState:
    s = StreamState(schedule, hist, route_mode)
    s.set_context(**day_context(date, meta.loc[date]))
    return s


def collect(files, schedule, hist, route_mode, meta, sample, rng):
    Xs, Ms = [], []
    for f in files:
        date = repo.fact_day_date(f)
        df = repo.read_fact_day(f)
        X, M = run_day(make_state(schedule, hist, route_mode, date, meta), df, sample, rng)
        M["date"] = date
        Xs.append(X)
        Ms.append(M)
        print(f"  {date}: {len(X):>8,} примеров, доля опозданий через 12 мин: {M.y.mean():.2f}")
    return pd.concat(Xs, ignore_index=True), pd.concat(Ms, ignore_index=True)


REG_FIT_ROWS = 600_000   # сколько строк берем на обучение регрессии (ограничение по памяти)


def cached(name, files, schedule, hist, route_mode, meta, sample, rng):
    """Признаки считаются долго, поэтому результат прогона потока кладем рядом с данными.
    Удалите data/processed/features_*.parquet, чтобы пересчитать."""
    fx, fm = PROC / f"features_{name}_X.parquet", PROC / f"features_{name}_M.parquet"
    if fx.exists() and fm.exists():
        print(f"  берем из кэша: {fx.name}")
        return pd.read_parquet(fx), pd.read_parquet(fm)
    X, M = collect(files, schedule, hist, route_mode, meta, sample, rng)
    X.to_parquet(fx, index=False)
    M.to_parquet(fm, index=False)
    return X, M


def main():
    rng = random.Random(RANDOM_SEED)
    files = repo.list_fact_days()
    meta = repo.read_sim_meta()
    routes = repo.read_routes()
    route_mode = repo.route_mode_map(routes)
    schedule = load_schedule_index(repo.read_stop_times())

    prof, train_f, test_f = files[:7], files[7:21], files[21:]
    print("Профиль перегонов по", len(prof), "дням")
    hist = build_hist_profile([repo.read_fact_day(f) for f in prof])

    print("Обучающая выборка:")
    Xtr, Mtr = cached("train", train_f, schedule, hist, route_mode, meta, 0.3, rng)
    print("Тестовая выборка:")
    Xte, Mte = cached("test", test_f, schedule, hist, route_mode, meta, 0.5, rng)

    # валидация для ранней остановки — последние 3 дня обучения
    va = (Mtr["date"] >= sorted(Mtr["date"].unique())[-3]).to_numpy()
    predictor = DelayPredictor.new(iterations=800, depth=8, learning_rate=0.08, loss_function="Logloss",
                                    eval_metric="PRAUC", od_type="Iter", od_wait=60,
                                    random_seed=RANDOM_SEED, verbose=100, thread_count=-1)
    predictor.fit(Xtr[~va], Mtr.y[~va], eval_set=(Xtr[va], Mtr.y[va]))

    p = predictor.predict_risk(Xte)
    y = Mte.y.to_numpy()
    # «ранние» случаи: сейчас машина еще НЕ опаздывает — ради них и нужна система
    early = (Xte["delay_now"] < LATE_THRESHOLD_MIN).to_numpy()

    res = {"all": [metrics(y, p, "CatBoost"),
                   metrics(y, Xte["delay_now"], "Базовое правило: текущая задержка")],
           "early_warning": [metrics(y[early], p[early], "CatBoost"),
                             metrics(y[early], Xte["delay_now"][early],
                                     "Базовое правило: текущая задержка")],
           "n_test": int(len(y)), "n_test_early": int(early.sum())}

    # --- основная метрика оценки: MAE отклонения в минутах ---
    # MAE-обучение заметно прожорливее по памяти, поэтому берем подвыборку обучающих строк
    import numpy as np
    ytr_min, yte_min = Mtr.delay_future.to_numpy(), Mte.delay_future.to_numpy()
    fit_idx = np.flatnonzero(~va)
    if len(fit_idx) > REG_FIT_ROWS:
        fit_idx = np.random.default_rng(RANDOM_SEED).choice(fit_idx, REG_FIT_ROWS, replace=False)
    reg = DelayRegressor.new(iterations=700, depth=6, learning_rate=0.1,
                             loss_function="MAE", eval_metric="MAE", od_type="Iter", od_wait=60,
                             border_count=32, boosting_type="Plain",
                             random_seed=RANDOM_SEED, verbose=100, thread_count=-1)
    reg.fit(Xtr.iloc[fit_idx], ytr_min[fit_idx], eval_set=(Xtr[va], ytr_min[va]))
    pred_min = reg.predict_delay(Xte)

    median_delay = float(np.median(ytr_min))
    preds = {"CatBoost (MAE-loss)": pred_min,
             **baselines(Xte["delay_now"].to_numpy(), median_delay, len(yte_min))}
    res["mae"] = [mae_report(yte_min, preds, "все машины"),
                  mae_report(yte_min[early], {k: np.asarray(v, float)[early] for k, v in preds.items()},
                             f"идут по графику (< {LATE_THRESHOLD_MIN:.0f} мин)"),
                  mae_report(yte_min[~early], {k: np.asarray(v, float)[~early] for k, v in preds.items()},
                             "уже опаздывают")]
    res["mae_by_delay"] = mae_by_bucket(yte_min, preds)
    res["mae_bias_min"] = round(float(np.mean(pred_min - yte_min)), 3)
    res["feature_importance_regressor"] = reg.feature_importance().round(2).to_dict()

    res["risk_levels"] = risk_levels(y, p)
    res["feature_importance"] = predictor.feature_importance().round(2).to_dict()
    res["feature_descriptions"] = FEATURE_DESCRIPTIONS

    MODELS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    predictor.save(MODELS / "delay_catboost.cbm")
    reg.save(MODELS / "delay_regressor.cbm")
    with open(MODELS / "hist_profile.pkl", "wb") as fh:
        pickle.dump(hist, fh)
    with open(REPORTS / "metrics.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
