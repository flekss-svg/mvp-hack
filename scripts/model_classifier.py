"""Задача 5.1: классификатор вероятностей early / ontime / late на признаках v2.

Сравнение на test с правилом «класс по прогнозу регрессора». Регрессор и классификатор для
сравнения обучены только на train; финальный классификатор (train + test) сохраняется в
models/hackathon_v2_classifier.cbm.
Запуск из корня проекта: python scripts/model_classifier.py"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from catboost import CatBoostClassifier, CatBoostRegressor

from ml_service.features import CLASSES, DATA, EARLY_S, LATE_S, delay_class, full_features, load_plan, load_points, load_traffic
from ml_service.models import CLASSIFIER_PATH, CLF_PARAMS, REG_PARAMS, fit_classifier, fit_regressor, mae, predict_class_probs


def features(part, labels, plan_file):
    pts = load_points(DATA / labels)
    return pts, full_features(pts, load_traffic(DATA / part / "traffic.csv"), load_plan(DATA / part / plan_file))


def laplace_class_probs(pred, b):
    """Мягкие вероятности для правила «по регрессору»: остаток ~ Laplace(0, b)."""
    def cdf(x):
        z = (x - pred) / b
        return np.where(z < 0, 0.5 * np.exp(z), 1 - 0.5 * np.exp(-z))
    p_early, p_late = cdf(EARLY_S), 1 - cdf(LATE_S)
    return np.column_stack([p_early, 1 - p_early - p_late, p_late])


def class_logloss(y_true, proba):
    """log_loss сортирует метки лексикографически, а столбцы proba идут в порядке CLASSES, поэтому — индексы."""
    idx = pd.Series(y_true).map({c: i for i, c in enumerate(CLASSES)}).to_numpy()
    return log_loss(idx, np.asarray(proba), labels=[0, 1, 2])


def report(name, y_true, hard, proba=None):
    f1 = f1_score(y_true, hard, labels=list(CLASSES), average=None, zero_division=0)
    ll = f"{class_logloss(y_true, proba):.3f}" if proba is not None else "  —  "
    print(f"  {name:34s} logloss {ll}  acc {accuracy_score(y_true, hard):.3f}  "
          f"F1 macro {f1.mean():.3f}  (early {f1[0]:.2f} / ontime {f1[1]:.2f} / late {f1[2]:.2f})")


tr_pts, Xtr = features("train", "labels/labels_train.csv", "schedule.csv")
te_pts, Xte = features("test", "labels/labels_test.csv", "schedule.csv")
Xte = Xte.reindex(columns=Xtr.columns)
ytr, yte = tr_pts["target_delay_s"].to_numpy(float), te_pts["target_delay_s"].to_numpy(float)
ctr, cte = tr_pts["target_class"].to_numpy(), te_pts["target_class"].to_numpy()
assert (delay_class(ytr) == ctr).all() and (delay_class(yte) == cte).all(), "target_class не совпадает с порогами"

print("Обучение (только train, GroupKFold по tr_id)...", flush=True)
clf, n_clf = fit_classifier(Xtr, ctr, tr_pts["tr_id"])
reg, n_reg = fit_regressor(Xtr, ytr, tr_pts["tr_id"])
print(f"  деревьев: классификатор {n_clf}, регрессор {n_reg}")

# масштаб остатков регрессора — по out-of-fold прогнозам train (test не трогаем)
oof = np.zeros(len(ytr))
for a, b in GroupKFold(5).split(Xtr, ytr, tr_pts["tr_id"]):
    oof[b] = CatBoostRegressor(iterations=n_reg, **REG_PARAMS).fit(Xtr.iloc[a], ytr[a]).predict(Xtr.iloc[b])
b_scale = float(np.mean(np.abs(ytr - oof)))

proba_clf = predict_class_probs(Xte, clf)
pred_reg = reg.predict(Xte)
hard_rule = delay_class(pred_reg)
prior = pd.Series(ctr).value_counts(normalize=True).reindex(CLASSES).to_numpy()

print(f"\n=== TEST: {len(yte)} точек, классы early/ontime/late = "
      f"{[int((cte == c).sum()) for c in CLASSES]} ===")
print(f"  MAE регрессора (для справки): {mae(yte, pred_reg):.2f} с;  масштаб остатков Laplace b = {b_scale:.1f} с")
report("классификатор CatBoost MultiClass", cte, proba_clf.idxmax(axis=1).to_numpy(), proba_clf.to_numpy())
report("правило: класс по регрессору", cte, hard_rule, laplace_class_probs(pred_reg, b_scale))
report("правило: класс по cur_dev_s", cte, delay_class(te_pts["cur_dev_s"]))
report("константа: доли классов train", cte, np.full(len(cte), "ontime"), np.tile(prior, (len(cte), 1)))
print("  (у правила logloss посчитан на мягких вероятностях Laplace вокруг прогноза регрессора)")

print("\nМатрица ошибок классификатора (строки — факт, столбцы — прогноз):")
cm = pd.DataFrame(confusion_matrix(cte, proba_clf.idxmax(axis=1), labels=list(CLASSES)),
                  index=[f"факт {c}" for c in CLASSES], columns=[f"прогноз {c}" for c in CLASSES])
print(cm.to_string())
print("Матрица ошибок правила «по регрессору»:")
cm = pd.DataFrame(confusion_matrix(cte, hard_rule, labels=list(CLASSES)),
                  index=[f"факт {c}" for c in CLASSES], columns=[f"прогноз {c}" for c in CLASSES])
print(cm.to_string())

print("\n=== Важность признаков классификатора (топ-12) ===")
imp = pd.Series(clf.get_feature_importance(), index=Xtr.columns).sort_values(ascending=False)
for k, v in imp.head(12).items():
    print(f"  {k:20s} {v:6.1f}")

final = CatBoostClassifier(iterations=n_clf, **CLF_PARAMS)
final.fit(pd.concat([Xtr, Xte], ignore_index=True), np.concatenate([ctr, cte]))
final.save_model(str(CLASSIFIER_PATH))
print(f"\nМодель (train + test, {n_clf} деревьев) сохранена: {CLASSIFIER_PATH.relative_to(CLASSIFIER_PATH.parent.parent)}")
