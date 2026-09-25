"""Задача 1: загрузка данных хакатона, проверки и простые правила на test.
Запуск из корня проекта: python scripts/explore.py
Печатает только сводные цифры."""
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).resolve().parent.parent / "data" / "hackathon"


def to_ts(s: pd.Series) -> pd.Series:
    """Время -> Unix-секунды. Работает и для чисел, и для строк, при любой точности pandas."""
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.99:
        num = num.astype("float64")
        return (num / 1000 if num.median() > 1e11 else num).round().astype("int64")
    dt = pd.to_datetime(s, errors="coerce", utc=True)
    return ((dt - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).astype("Int64")


def mae(y, p):
    return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))


def section(t):
    print(f"\n=== {t} ===")


# --- метки ---
lab_tr = pd.read_csv(D / "labels" / "labels_train.csv")
lab_te = pd.read_csv(D / "labels" / "labels_test.csv")
pts_va = pd.read_csv(D / "validate" / "points.csv")
sub = pd.read_csv(D / "sample_submission.csv", sep=";")

section("Размеры")
for n, df in [("labels_train", lab_tr), ("labels_test", lab_te), ("validate/points", pts_va), ("sample_submission", sub)]:
    print(f"{n:18s} {len(df):>9,} строк, колонки: {list(df.columns)}")

section("Проверки целостности")
for n, df in [("labels_train", lab_tr), ("labels_test", lab_te), ("validate/points", pts_va)]:
    print(f"{n:18s} дубли sample_id: {df.sample_id.duplicated().sum()}, "
          f"пропуски: {int(df.isna().sum().sum())}, машин: {df.tr_id.nunique():,}")
same = set(sub.sample_id) == set(pts_va.sample_id)
print(f"sample_submission покрывает ровно validate/points: {same}")

section("Время и горизонт")
for n, df in [("labels_train", lab_tr), ("labels_test", lab_te), ("validate/points", pts_va)]:
    T, tb = to_ts(df["T"]), to_ts(df["target_time_begin"])
    h = (tb - T) / 60
    print(f"{n:18s} T: {pd.to_datetime(T.min(), unit='s')} .. {pd.to_datetime(T.max(), unit='s')}, "
          f"горизонт мин: {h.min():.1f}..{h.max():.1f} (медиана {h.median():.1f})")

section("Цель (секунды)")
for n, df in [("train", lab_tr), ("test", lab_te)]:
    y = df.target_delay_s
    print(f"{n:6s} медиана {y.median():6.1f}  среднее {y.mean():6.1f}  "
          f"p5 {y.quantile(.05):6.1f}  p95 {y.quantile(.95):6.1f}  мин {y.min():6.0f}  макс {y.max():6.0f}")
    print(f"       классы: {df.target_class.value_counts(normalize=True).round(3).to_dict()}")

section("Простые правила на TEST (это наша локальная проверка)")
y = lab_te.target_delay_s
res = {"ноль": mae(y, 0), "cur_dev_s (baseline организаторов)": mae(y, lab_te.cur_dev_s),
       "медиана train": mae(y, lab_tr.target_delay_s.median())}
for k, v in res.items():
    print(f"{k:36s} MAE = {v:7.2f} c")
print(f"Связь cur_dev_s и цели: корреляция {np.corrcoef(lab_te.cur_dev_s, y)[0, 1]:.3f}")

section("Телеметрия (первые 200 тыс. строк каждого файла)")
for part in ["train", "test", "validate"]:
    tr = pd.read_csv(D / part / "traffic.csv", nrows=200_000)
    print(f"{part:8s} колонки: {list(tr.columns)}")
    print(f"         location_valid=True: {tr.location_valid.astype(str).str.lower().eq('true').mean():.1%}, "
          f"скорость медиана {tr.speed.median():.1f} км/ч, стоит (<3 км/ч): {(tr.speed < 3).mean():.1%}")
    
section("Как записано время (по одному значению)")
sch = pd.read_csv(D / "train" / "schedule.csv", nrows=3)
tr = pd.read_csv(D / "train" / "traffic.csv", nrows=3, dtype={"packet_id": str})
print("labels_train T:                ", repr(lab_tr["T"].iloc[0]))
print("labels_train target_time_begin:", repr(lab_tr["target_time_begin"].iloc[0]))
print("labels_test  T:                ", repr(lab_te["T"].iloc[0]))
print("labels_test  target_time_begin:", repr(lab_te["target_time_begin"].iloc[0]))
print("traffic      event_time:       ", repr(tr["event_time"].iloc[0]))
print("schedule     time_begin:       ", repr(sch["time_begin"].iloc[0]))
print("sample_id:                     ", repr(lab_tr["sample_id"].iloc[0]))