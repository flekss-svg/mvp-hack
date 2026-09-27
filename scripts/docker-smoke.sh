#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    docker compose ps || true
    docker compose logs --no-color || true
  fi
  docker compose down --remove-orphans || true
  exit "$status"
}
trap cleanup EXIT INT TERM

docker compose up -d --build ml backend web

attempt=0
until curl --fail --silent http://localhost:8000/api/health > docker-health.json; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "Docker stack did not become ready in 5 minutes" >&2
    exit 1
  fi
  sleep 5
done

python -c 'import json; d=json.load(open("docker-health.json", encoding="utf-8")); expected=("replay","live","ndtp","forecast"); assert all(d["sources"][k]["ready"] for k in expected), d; assert d["sources"]["forecast"]["mode"] == "service", d'
curl --fail --silent --output /dev/null http://localhost:8000/
curl --fail --silent --output /dev/null http://localhost:8000/docs
curl --fail --silent --output /dev/null http://localhost:8000/openapi.json

echo "Docker smoke checks passed."
