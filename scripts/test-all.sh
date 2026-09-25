#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
unset NO_COLOR || true

if [ -x "venv/Scripts/python.exe" ]; then
  PYTHON="venv/Scripts/python.exe"
elif [ -x "venv/bin/python" ]; then
  PYTHON="venv/bin/python"
else
  PYTHON="python"
fi

echo "[1/5] Backend unit tests"
"$PYTHON" -m coverage erase
"$PYTHON" -m pytest tests/unit -m unit --cov=app --cov-report=
echo "[2/5] Backend API integration + coverage gate (minimum 80%)"
"$PYTHON" -m pytest tests/integration -m integration --cov=app --cov-append --cov-report=term-missing --cov-fail-under=80
echo "[3/5] Frontend unit/component tests + coverage gate"
npm --prefix web run test:run
echo "[4/5] TypeScript check and production build"
npm --prefix web run build
echo "[5/5] Full-stack Playwright smoke/E2E"
npm --prefix web run test:e2e

echo "All pre-push checks passed."
