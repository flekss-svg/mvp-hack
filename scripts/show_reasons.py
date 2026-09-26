"""Задача 5.2: примеры «прогноз -> причины» на test и покрытие причин.
Модель — сохранённый v2 (учился на train + test), поэтому на test это проверка здравого смысла
текстов, а не оценка качества.
Запуск из корня проекта: python scripts/show_reasons.py"""
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_service.features import DATA, full_features, load_plan, load_points, load_traffic
from ml_service.reasons import MIN_SHIFT_S, explain, load_regressor, shap_values

pts = load_points(DATA / "labels" / "labels_test.csv")
X = full_features(pts, load_traffic(DATA / "test" / "traffic.csv"), load_plan(DATA / "test" / "schedule.csv"))
model = load_regressor()
X = X[model.feature_names_]
pred = model.predict(X)
reasons = explain(X, top_k=3)

print(f"=== 10 примеров на test (по возрастанию прогноза), базовое значение SHAP "
      f"{shap_values(X.iloc[:1])[1][0]:.0f} с ===")
for i in np.linspace(0, len(X) - 1, 10).round().astype(int):
    j = np.argsort(pred)[i]
    print(f"\n#{j}: прогноз {pred[j]:+.0f} с (сейчас {X['cur_dev_s'].iloc[j]:+.0f} с, до цели "
          f"{X['n_stops_ahead'].iloc[j]:.0f} ост.)")
    print("   причины:", "; ".join(reasons[j]) if reasons[j] else "— (прогноз близок к типичному)")

shifted = np.abs(pred - shap_values(X)[1]) >= MIN_SHIFT_S
have = np.array([len(r) > 0 for r in reasons])
print("\n=== Покрытие на test ===")
print(f"  прогнозов со сдвигом ≥ {MIN_SHIFT_S} с: {shifted.mean():.0%}; из них с ≥1 причиной: "
      f"{have[shifted].mean():.0%}; среднее число причин: {np.mean([len(r) for r in reasons]):.2f}")
cnt = Counter(t.split(" (")[0].split(" на ")[0] for r in reasons for t in r)
print("  частота фраз:")
for t, n in cnt.most_common():
    print(f"    {n:4d}  {t}")
