#!/usr/bin/env sh
# Собрать и поднять Docker-стек, проверить его и остановить (запускается и в CI).
# Прогноз по NDTP (forecast) требует данных организаторов: если data/hackathon/ пуста,
# проверяется только, что ML-модуль работает отдельным сервисом.
set -eu

cd "$(dirname "$0")/.."
. scripts/python.sh

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    docker compose ps || true
    docker compose logs --no-color --tail 50 || true
  fi
  docker compose down --remove-orphans || true
  exit "$status"
}
trap cleanup EXIT INT TERM

docker compose up -d --build ml backend web

attempt=0
until curl --fail --silent http://localhost:8000/api/health > /tmp/docker-health.json; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "Docker-стек не поднялся за 5 минут" >&2
    exit 1
  fi
  sleep 5
done

if [ -f data/hackathon/train/schedule.csv ]; then EXPECT_FORECAST=1; else EXPECT_FORECAST=0; fi
# ML-модуль грузит модели и данные не мгновенно: ждем его готовности до 2 минут
attempt=0
while :; do
  curl --fail --silent http://localhost:8000/api/health > /tmp/docker-health.json
  "$PYTHON" - "$EXPECT_FORECAST" <<'EOF' && break
import json, sys
d = json.load(open("/tmp/docker-health.json", encoding="utf-8"))["sources"]
for k in ("replay", "live", "ndtp"):
    assert d[k]["ready"], (k, d[k])
assert d["forecast"]["mode"] == "service", d["forecast"]
assert sys.argv[1] == "0" or d["forecast"]["ready"], d["forecast"]
EOF
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 24 ]; then
    cat /tmp/docker-health.json >&2
    exit 1
  fi
  sleep 5
done

curl --fail --silent --output /dev/null http://localhost:8000/
curl --fail --silent --output /dev/null http://localhost:8000/docs
curl --fail --silent --output /dev/null http://localhost:8000/openapi.json
curl --fail --silent --output /dev/null http://localhost:8000/api/replay/day

if [ "$EXPECT_FORECAST" = 1 ]; then
  echo "Docker smoke пройден (с прогнозом по данным хакатона)."
else
  echo "Docker smoke пройден. data/hackathon/ пуста — готовность прогноза не проверялась."
fi
