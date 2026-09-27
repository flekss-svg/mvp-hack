"""Проверка map matching (ml_service/map_matching.py): угадывает ли алгоритм рейс по треку.

Таблица unit_id -> tr_id от алгоритма скрыта: для каждой машины из traffic.csv каждые 5 минут берется
трек за последние 10 минут и сравнивается с плановыми нитками всех рейсов. Правильный ответ — tr_id
машины, если для него есть расписание; у машин без расписания правильный ответ — «не привязывать».

Две оценки:
  * по моментам: доля правильных и ложных привязок по отдельному треку;
  * как в потоке: машина привязывается после CONFIRM совпадений подряд и дальше остается привязанной;
    считается доля времени, когда привязка верна, ошибочна или ее еще нет.
Пороги подбирались на train; test — итоговая проверка.
Запуск из корня проекта: python scripts/check_map_matching.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_service import map_matching as mm
from ml_service.features import DATA, load_traffic
from ml_service.live import load_assets

STEP_S = 300


def moments(part: str, index: mm.TripIndex) -> dict:
    """tr_id машины -> [(истинный рейс или None, выбранный рейс или None), ...] по времени."""
    out = {}
    for vid, v in load_traffic(DATA / part / "traffic.csv").items():
        truth = vid if vid in index.trips else None
        t = v["t"].astype(float)
        seq = []
        for T in np.arange(t[0] + mm.WINDOW_S, t[-1], STEP_S):
            m = t <= T
            if m.sum() < mm.MIN_FIXES:
                continue
            tr = mm.track(t[m], v["lat"][m], v["lon"][m], v["valid"][m])
            seq.append(mm.choose(mm.candidates(*tr, index)) if tr is not None else None)
        out[vid] = (truth, [c["tr_id"] if c else None for c in seq])
    return out


def report(part: str, res: dict) -> None:
    tp = fp = n_truth = nop_fp = 0
    bound_ok = bound_wrong = unbound = 0
    for truth, picks in res.values():
        streak, bound = (None, 0), None
        for p in picks:
            if truth is None:
                nop_fp += p is not None
            else:
                n_truth += 1
                tp += p == truth
                fp += p is not None and p != truth
            streak = (p, streak[1] + 1) if p is not None and p == streak[0] else ((p, 1) if p else (None, 0))
            if bound is None and streak[0] and streak[1] >= mm.CONFIRM:
                bound = streak[0]
            if truth is not None:
                bound_ok += bound == truth
                bound_wrong += bound is not None and bound != truth
                unbound += bound is None
    with_plan = sum(truth is not None for truth, _ in res.values())
    print(f"=== {part}: машин с расписанием {with_plan}, без расписания {len(res) - with_plan} ===")
    print(f"  по моментам: верно {tp / n_truth:.1%}, ложно {fp / max(tp + fp, 1):.1%} от привязок "
          f"(точность {tp / max(tp + fp, 1):.1%}); у машин без расписания ложных привязок {nop_fp}")
    n = bound_ok + bound_wrong + unbound
    print(f"  как в потоке (подтверждение {mm.CONFIRM} раза): привязка верна {bound_ok / n:.1%} времени, "
          f"ошибочна {bound_wrong / n:.1%}, еще нет {unbound / n:.1%}")


if __name__ == "__main__":
    plan, _, _ = load_assets()
    index = mm.TripIndex(plan)
    for part in ("train", "test"):
        report(part, moments(part, index))
