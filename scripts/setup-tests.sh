#!/usr/bin/env sh
# Первичная настройка: venv, зависимости Python и npm, Chromium для Playwright, pre-push хук.
# На Windows запускать из Git Bash.
set -eu

cd "$(dirname "$0")/.."
unset NO_COLOR || true

if [ ! -x "venv/bin/python" ] && [ ! -x "venv/Scripts/python.exe" ]; then
  if command -v python3 >/dev/null 2>&1; then python3 -m venv venv; else python -m venv venv; fi
fi
. scripts/python.sh

"$PYTHON" -m pip install -r requirements-dev.txt
npm --prefix web install
(cd web && npx playwright install chromium)
chmod +x .githooks/pre-push scripts/setup-tests.sh scripts/test-all.sh run_all.sh
git config core.hooksPath .githooks

echo "Test environment is ready. Run ./scripts/test-all.sh"
