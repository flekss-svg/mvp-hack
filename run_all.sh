#!/usr/bin/env bash
# Полный прогон MVP. CSV с data.mos.ru положить в data/raw/ (наборы 60661, 60662, 60664, 60665, 60666).
set -e
cd "$(dirname "$0")/src"
python load_schedule.py      # CSV -> parquet, подвыборка маршрутов
python simulate.py           # синтетический факт (убрать, когда будет телематика)
python ingest.py             # самопроверка адаптера GPS -> остановки
python train.py              # признаки, обучение, метрики -> reports/metrics.json
python export_dashboard.py   # прогон тестового дня -> dashboard/dashboard.html
