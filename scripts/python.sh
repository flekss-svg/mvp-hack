# Подключается через `. scripts/python.sh`: выставляет PYTHON.
# Порядок: venv проекта (macOS/Linux и Windows/Git Bash), затем python3, затем python.
# На macOS команды `python` обычно нет — только `python3`.
for candidate in venv/bin/python venv/Scripts/python.exe; do
  if [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
done
if [ -z "${PYTHON:-}" ]; then
  if command -v python3 >/dev/null 2>&1; then PYTHON=python3; else PYTHON=python; fi
fi
export PYTHON
