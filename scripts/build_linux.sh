#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv-build}"

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required")
if sys.version_info >= (3, 14):
    print("WARNING: Python 3.14+ may not have wheels for PyInstaller/PyVista/VTK yet.")
    print("         Prefer Python 3.11 or 3.12 for release builds.")
PY

"$PYTHON_BIN" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
python -m compileall -q main.py app scripts tests
pyinstaller packaging/split3r.spec --clean --noconfirm

printf '\nBuild ready at: %s/dist/Split3rClone\n' "$ROOT_DIR"
