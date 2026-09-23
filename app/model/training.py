"""Обучение предиктора задержек и честная оценка против простого базового правила.

Разбиение по времени (никакой перемешки дней):
  дни 1–7   — «профильные»: считаем типичное время хода по перегонам и часам
  дни 8–21  — обучение
  дни 22–28 — тест

Использует только canonical-слои: data_sources (доступ к данным), engine (признаки),
model.predictor/evaluation (обучение и оценка). Не знает деталей формата CSV data.mos.ru
и не дублирует код загрузки признаков с service/risk_service.py или dashboard_export.py.
"""
import json
import pickle
import random

import pandas as pd

from app.config import HOLIDAYS, LATE_THRESHOLD_MIN, MODELS, RANDOM_SEED, REPORTS
from app.data_sources import processed_repository as repo
from app.domain.schema import DayContext
from app.engine.feature_definitions import FEATURE_DESCRIPTIONS
from app.engine.stream_state import StreamState, build_hist_profile, load_schedule_index, run_day
from app.model.evaluation import metrics, risk_levels
from app.model.predictor import DelayPredictor


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
    Xtr, Mtr = collect(train_f, schedule, hist, route_mode, meta, 0.3, rng)
    print("Тестовая выборка:")
    Xte, Mte = collect(test_f, schedule, hist, route_mode, meta, 0.5, rng)

    # валидация для ранней остановки — последние 3 дня обучения
    va = Mtr["date"] >= sorted(Mtr["date"].unique())[-3]
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

    res["risk_levels"] = risk_levels(y, p)
    res["feature_importance"] = predictor.feature_importance().round(2).to_dict()
    res["feature_descriptions"] = FEATURE_DESCRIPTIONS

    MODELS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    predictor.save(MODELS / "delay_catboost.cbm")
    with open(MODELS / "hist_profile.pkl", "wb") as fh:
        pickle.dump(hist, fh)
    with open(REPORTS / "metrics.json", "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
