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
# clean previous build outputs to avoid stale artifacts
rm -rf "$WD/dist" "$WD/build" "$WD"/*.egg-info || true

"$VENV_DIR/bin/python" -m pip install --upgrade build
"$VENV_DIR/bin/python" -m build

echo "Running twine check on built artifacts (metadata/sanity)"
"$VENV_DIR/bin/python" -m pip install --upgrade twine >/dev/null 2>&1 || true
"$VENV_DIR/bin/python" -m twine check dist/* || true

echo "Verifying artifact installability in a fresh venv"
# create a temporary venv for artifact verification
VERIFY_TMP_DIR="$(mktemp -d -t verify-venv-XXXXXXXX)"
VERIFY_VENV="$VERIFY_TMP_DIR/venv"
python3 -m venv "$VERIFY_VENV"
"$VERIFY_VENV/bin/python" -m pip install --upgrade pip

# prefer wheel if present, otherwise fall back to sdist
if ls "$WD/dist"/*.whl >/dev/null 2>&1; then
  "$VERIFY_VENV/bin/python" -m pip install "$WD/dist"/*.whl
else
  "$VERIFY_VENV/bin/python" -m pip install "$WD/dist"/*.tar.gz
fi

echo "Running quick smoke test from installed artifact"
# adjust the import below to a small, fast check for this package
"$VERIFY_VENV/bin/python" -c "import neo_rx; print('artifact-import-ok', getattr(neo_rx, '__version__', 'no-version'))"

# cleanup temporary verification venv
rm -rf "$VERIFY_TMP_DIR"

echo "Verification completed successfully. Clean up by removing $VENV_DIR when done."
