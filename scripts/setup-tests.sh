#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
unset NO_COLOR || true

if [ ! -x "venv/bin/python" ] && [ ! -x "venv/Scripts/python.exe" ]; then
  python -m venv venv
fi
if [ -x "venv/bin/python" ]; then
  PYTHON="venv/bin/python"
else
  PYTHON="venv/Scripts/python.exe"
fi

"$PYTHON" -m pip install -r requirements-dev.txt
npm --prefix web install
(cd web && npx playwright install chromium)
chmod +x .githooks/pre-push scripts/setup-tests.sh scripts/test-all.sh
git config core.hooksPath .githooks

echo "Test environment is ready. Run ./scripts/test-all.sh"
