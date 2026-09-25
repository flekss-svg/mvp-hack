#!/usr/bin/env sh
# Полный прогон MVP. CSV с data.mos.ru положить в data/raw/ (наборы 60661, 60662, 60664, 60665, 60666).
set -eu
cd "$(dirname "$0")"
. scripts/python.sh
"$PYTHON" -m app.data_sources.mos_ru_schedule    # CSV -> parquet, подвыборка маршрутов
"$PYTHON" -m app.simulation.synthetic_telemetry  # синтетический факт (убрать, когда будет телематика)
"$PYTHON" -m app.data_sources.gps_telemetry      # самопроверка адаптера GPS -> остановки
"$PYTHON" -m app.model.training                  # признаки, обучение, метрики -> reports/metrics.json
"$PYTHON" -m app.replay_build                    # прогон тестового дня -> кэш демо-дня для API
npm --prefix web install && npm --prefix web run build   # дашборд -> web/dist, отдается API
