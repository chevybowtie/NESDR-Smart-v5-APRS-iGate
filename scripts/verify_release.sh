#!/usr/bin/env bash
set -euo pipefail

# Lightweight verification script used locally and in CI to validate
# the project after dependency or packaging changes.
#
# Actions performed:
#  - create a clean virtualenv in .venv-check
#  - install the project with extras (direwolf,dev)
#  - run ruff (format/lint) if available
#  - run pytest
#  - run mypy (optional, enabled by setting RUN_MYPY=1)
#  - build wheel with python -m build

WD="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$WD/.venv-check"

if [ -d "$VENV_DIR" ]; then
  echo "Removing existing $VENV_DIR"
  rm -rf "$VENV_DIR"
fi

echo "Creating venv at $VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip

echo "Installing project (editable) with extras: direwolf,dev"
"$VENV_DIR/bin/python" -m pip install -e ".[direwolf,dev]"

echo "Running ruff (format + lint checks) if available"
if "$VENV_DIR/bin/python" -m ruff --version >/dev/null 2>&1; then
  "$VENV_DIR/bin/python" -m ruff check src tests || true
else
  echo "ruff not available in venv; skipping lint step"
fi

echo "Running pytest"
"$VENV_DIR/bin/python" -m pytest -q

if [ "${RUN_MYPY:-0}" = "1" ]; then
  echo "Running mypy (RUN_MYPY=1)"
  "$VENV_DIR/bin/python" -m mypy src || {
    echo "mypy failed" >&2
    exit 2
  }
fi

echo "Installing build helper and building wheel"
"$VENV_DIR/bin/python" -m pip install --upgrade build
"$VENV_DIR/bin/python" -m build

echo "Verification completed successfully. Clean up by removing $VENV_DIR when done."
