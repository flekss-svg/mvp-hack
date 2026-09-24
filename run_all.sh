#!/usr/bin/env bash
# Полный прогон MVP. CSV с data.mos.ru положить в data/raw/ (наборы 60661, 60662, 60664, 60665, 60666).
set -e
cd "$(dirname "$0")"
python -m app.data_sources.mos_ru_schedule    # CSV -> parquet, подвыборка маршрутов
python -m app.simulation.synthetic_telemetry  # синтетический факт (убрать, когда будет телематика)
python -m app.data_sources.gps_telemetry      # самопроверка адаптера GPS -> остановки
python -m app.model.training                  # признаки, обучение, метрики -> reports/metrics.json
python -m app.replay_build                    # прогон тестового дня -> кэш демо-дня для API
(cd web && npm install && npm run build)      # сборка дашборда -> web/dist, отдается API
