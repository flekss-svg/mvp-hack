"""Причины прогноза: SHAP-вклады признаков -> короткие фразы для диспетчера.

Как читать словарь REASONS (править можно без программиста):
  * ключ — имя признака из ml_service/features.py;
  * "group" — признаки одной группы считаются вместе: их SHAP-вклады складываются, а в ответ
    попадает одна фраза на группу (сильно связанные признаки иначе дают противоречивые вклады:
    например, расстояние по прямой и по маршруту);
  * "late"  — фраза, если признак толкает прогноз к опозданию (задержка больше типичной);
    "early" — фраза, если толкает к опережению;
  * у фразы: "text" и необязательные границы реального значения признака "min" / "max".
    Фраза выводится, только если значение признака их выполняет. Вместо одной фразы можно дать
    список: берётся первая, которая подходит по значению. Это защита от ложных утверждений:
    SHAP показывает сдвиг относительно *среднего* прогноза, а фраза «уже отстаёт от графика»
    говорит об *абсолютном* состоянии (машина с +10 с чуть опаздывает, но вклад у нее отрицательный);
  * в "text" можно подставлять {v} — значение, {a} — его модуль, {m} — модуль в минутах
    (для признаков в секундах);
  * признак без "late"/"early" только участвует в сумме группы и фразы не даёт.

Пороги подобраны по квантилям train (q10/q50/q90 в комментариях у признаков).
Признаки времени суток и горизонта в причины не выводятся (EXCLUDED): диспетчеру они ничего не говорят.
"""
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

from .models import REGRESSOR_PATH

EXCLUDED = {"tgt_min_of_day", "horizon_s"}
MIN_SHIFT_S = 5      # прогноз ближе к среднему, чем на столько секунд, — причин нет
MIN_CONTRIB_S = 3    # вклад группы меньше этого (в секундах) в причину не берём

REASONS = {
    # отставание на последней пройденной остановке. q10/q50/q90: -83 / 26 / 235 с
    "cur_dev_s": {
        "group": "dev",
        "late": {"text": "уже отстаёт от графика на {a:.0f} с", "min": 30},
        "early": [
            {"text": "идёт с опережением графика на {a:.0f} с", "max": -30},
            {"text": "сейчас идёт по графику ({v:+.0f} с)", "min": -30, "max": 30},
            {"text": "отставание пока небольшое ({a:.0f} с)", "min": 30, "max": 60},
        ],
    },
    # сколько остановок осталось до цели. q10/q50/q90: 4 / 7 / 9
    "n_stops_ahead": {
        "group": "route",
        "late": {"text": "много остановок до цели ({v:.0f})", "min": 8},
        "early": {"text": "мало остановок до цели ({v:.0f})", "max": 5},
    },
    # длина оставшегося пути по маршруту, м. q10/q50/q90: 1000 / 2900 / 5900
    "dist_route_m": {
        "group": "route",
        "late": {"text": "далеко до остановки: {v:.0f} м по маршруту", "min": 4000},
        "early": {"text": "остановка совсем рядом: {v:.0f} м по маршруту", "max": 1500},
    },
    # расстояние по прямой: у модели вклад противоположен маршрутному (они коллинеарны), фразы нет
    "dist_straight_m": {"group": "route"},

    # доля времени «стоит» (скорость < 3 км/ч). q10/q50/q90: 0.15 / 0.29 / 0.98 для окна 10 мин
    "stopped_share_600": {
        "group": "idle",
        "late": {"text": "долгий простой за последние 10 мин", "min": 0.5},
        "early": {"text": "почти без простоев за последние 10 мин", "max": 0.15},
    },
    "stopped_share_300": {
        "group": "idle",
        "late": {"text": "простой за последние 5 мин", "min": 0.5},
    },
    "stopped_share_120": {
        "group": "idle",
        "late": {"text": "почти стоит последние 2 мин", "min": 0.6},
    },

    # средняя скорость с учётом стоянок по координатам, м/с. q10/q50/q90: ~0.9 / 4.6 / 7.8
    "eff_speed_300": {
        "group": "progress",
        "late": {"text": "низкая скорость последние 5 мин", "max": 2.0},
        "early": {"text": "хорошая скорость последние 5 мин", "min": 6.5},
    },
    "eff_speed_600": {
        "group": "progress",
        "late": {"text": "низкая скорость последние 10 мин", "max": 2.0},
        "early": {"text": "хорошая скорость последние 10 мин", "min": 6.5},
    },
    "eff_speed_120": {
        "group": "progress",
        "late": {"text": "почти не продвигается последние 2 мин", "max": 1.5},
    },
    # поле speed из телеметрии часто равно 0 (медиана 0), поэтому фраз по нему нет
    "speed_last": {"group": "progress"},
    "speed_mean_120": {"group": "progress"},
    "speed_mean_300": {"group": "progress"},
    "speed_mean_600": {"group": "progress"},
    "path_m_120": {"group": "progress"},
    "path_m_300": {"group": "progress"},
    "path_m_600": {"group": "progress"},

    # какая скорость нужна, чтобы успеть по графику, м/с. q10/q50/q90: 1.5 / 4.4 / 8.8
    "req_speed": {
        "group": "req",
        "late": {"text": "чтобы успеть, надо ехать быстрее обычного ({v:.1f} м/с)", "min": 6.5},
    },

    # прогноз опоздания по текущей скорости, с
    "phys_delay_300": {
        "group": "phys",
        "late": {"text": "при текущей скорости не успевает к остановке", "min": 60},
        "early": {"text": "при текущей скорости придёт раньше графика", "max": -60},
    },
    "phys_delay_600": {
        "group": "phys",
        "late": {"text": "при скорости последних 10 мин не успевает к остановке", "min": 60},
        "early": {"text": "при скорости последних 10 мин придёт раньше графика", "max": -60},
    },
    # свежесть данных — техническая деталь, диспетчеру это не причина задержки
    "last_ping_age_s": {"group": "tech"},
    "pos_age_s": {"group": "tech"},
}

_model = None


def load_regressor(path=REGRESSOR_PATH) -> CatBoostRegressor:
    global _model
    if _model is None:
        _model = CatBoostRegressor().load_model(str(path))
    return _model


def shap_values(X: pd.DataFrame, model: CatBoostRegressor = None):
    """(вклады по признакам, базовое значение, прогноз): вклады + базовое = прогноз."""
    model = model or load_regressor()
    sh = model.get_feature_importance(data=Pool(X[model.feature_names_]), type="ShapValues")
    return pd.DataFrame(sh[:, :-1], columns=model.feature_names_, index=X.index), sh[:, -1], sh.sum(axis=1)


def _pick(alternatives, value: float):
    """Первая фраза из словаря (одна или список), чьи границы min/max выполняет значение признака."""
    if value is None or np.isnan(value):
        return None
    for cond in alternatives if isinstance(alternatives, list) else [alternatives]:
        if cond.get("min", -np.inf) <= value <= cond.get("max", np.inf):
            return cond
    return None


def explain(X: pd.DataFrame, top_k: int = 3, model: CatBoostRegressor = None) -> list:
    """Для каждой строки X — до top_k фраз-причин (пустой список, если прогноз почти типичный)."""
    contrib, base, pred = shap_values(X, model)
    groups = {}
    for feat, spec in REASONS.items():
        if feat in contrib.columns and feat not in EXCLUDED:
            groups.setdefault(spec["group"], []).append(feat)

    out = []
    for i in range(len(X)):
        shift = pred[i] - base[i]
        if abs(shift) < MIN_SHIFT_S:
            out.append([])
            continue
        side = "late" if shift > 0 else "early"
        sign = 1.0 if shift > 0 else -1.0
        row = contrib.iloc[i]
        ranked = sorted(groups.items(), key=lambda kv: -sign * row[kv[1]].sum())
        phrases = []
        for _, feats in ranked:
            if sign * row[feats].sum() < MIN_CONTRIB_S:
                break                                # дальше вклады только слабее
            cands = []
            for f in feats:
                cond = _pick(REASONS[f].get(side, []), float(X[f].iloc[i]))
                if cond:
                    cands.append((sign * row[f], f, cond))
            if cands:
                _, f, cond = max(cands, key=lambda c: c[0])
                v = float(X[f].iloc[i])
                phrases.append(cond["text"].format(v=v, a=abs(v), m=abs(v) / 60))
            if len(phrases) == top_k:
                break
        out.append(phrases)
    return out
