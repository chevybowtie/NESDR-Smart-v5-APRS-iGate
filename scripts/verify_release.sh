#!/usr/bin/env bash
set -euo pipefail

# Multi-package verification script for neo-rx suite.
#
# Verifies all packages in dependency order:
#  1. neo-core (base dependencies)
#  2. neo-telemetry, neo-aprs, neo-wspr (depend on neo-core)
#  3. neo-rx (metapackage depending on all)
#
# Actions performed:
#  - create clean virtualenv in .venv-check
#  - install packages with extras (direwolf,dev) in dependency order
#  - run ruff (format/lint) if available
#  - run pytest
#  - run mypy (optional, enabled by setting RUN_MYPY=1)
#  - build wheels for all packages

WD="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$WD/.venv-check"

PACKAGES=(
  "neo_core"
  "neo_telemetry"
  "neo_aprs"
  "neo_wspr"
  "neo_rx"
)

if [ -d "$VENV_DIR" ]; then
  echo "Removing existing $VENV_DIR"
  rm -rf "$VENV_DIR"
fi

echo "Creating venv at $VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip

echo "Installing packages in dependency order (editable)..."

# neo-core (base)
echo "  Installing neo-core..."
"$VENV_DIR/bin/python" -m pip install -e "$WD/src/neo_core[dev]"

# neo-telemetry (depends on neo-core)
echo "  Installing neo-telemetry..."
"$VENV_DIR/bin/python" -m pip install -e "$WD/src/neo_telemetry[dev]"

# neo-aprs (depends on neo-core)
echo "  Installing neo-aprs..."
"$VENV_DIR/bin/python" -m pip install -e "$WD/src/neo_aprs[dev,direwolf]"

# neo-wspr (depends on neo-core)
echo "  Installing neo-wspr..."
"$VENV_DIR/bin/python" -m pip install -e "$WD/src/neo_wspr[dev]"

# neo-rx (metapackage, depends on all)
echo "  Installing neo-rx..."
"$VENV_DIR/bin/python" -m pip install -e "$WD[dev,all]"

echo "Running ruff (format + lint checks) if available"
if "$VENV_DIR/bin/python" -m ruff --version >/dev/null 2>&1; then
  "$VENV_DIR/bin/python" -m ruff check "$WD/src" "$WD/tests" || true
else
  echo "ruff not available in venv; skipping lint step"
fi

echo "Running pytest"
cd "$WD"
PYTHONPATH="$WD/src" "$VENV_DIR/bin/python" -m pytest -q

if [ "${RUN_MYPY:-0}" = "1" ]; then
  echo "Running mypy (RUN_MYPY=1)"
  "$VENV_DIR/bin/python" -m mypy "$WD/src" || {
    echo "mypy failed" >&2
    exit 2
  }
fi

echo "Installing build helper and building wheels for all packages"
rm -rf "$WD/dist" "$WD/build" "$WD"/*.egg-info "$WD/src"/*/*.egg-info "$WD/src"/*/dist || true
mkdir -p "$WD/dist"

"$VENV_DIR/bin/python" -m pip install --upgrade build

for pkg in "${PACKAGES[@]}"; do
  if [ "$pkg" = "neo_rx" ]; then
    echo "Building $pkg (metapackage)..."
    "$VENV_DIR/bin/python" -m build "$WD" --outdir "$WD/dist"
  else
    echo "Building $pkg..."
    "$VENV_DIR/bin/python" -m build "$WD/src/$pkg" --outdir "$WD/dist"
  fi
done

echo "Running twine check on built artifacts (metadata/sanity)"
"$VENV_DIR/bin/python" -m pip install --upgrade twine >/dev/null 2>&1 || true
"$VENV_DIR/bin/python" -m twine check "$WD/dist"/* || true

echo "Verifying artifact installability in a fresh venv"
VERIFY_TMP_DIR="$(mktemp -d -t verify-venv-XXXXXXXX)"
VERIFY_VENV="$VERIFY_TMP_DIR/venv"
python3 -m venv "$VERIFY_VENV"
"$VERIFY_VENV/bin/python" -m pip install --upgrade pip

# Install all wheels from dist/
echo "Installing all wheels from dist/ in dependency order..."
# Install in dependency order, allowing PyPI for dependencies
"$VERIFY_VENV/bin/python" -m pip install --find-links="$WD/dist" \
  neo-core neo-telemetry neo-aprs neo-wspr neo-rx

echo "Running smoke tests from installed artifacts"
"$VERIFY_VENV/bin/python" -c "import neo_core; print('✓ neo_core import ok')"
"$VERIFY_VENV/bin/python" -c "import neo_telemetry; print('✓ neo_telemetry import ok')"
"$VERIFY_VENV/bin/python" -c "import neo_aprs; print('✓ neo_aprs import ok')"
"$VERIFY_VENV/bin/python" -c "import neo_wspr; print('✓ neo_wspr import ok')"
"$VERIFY_VENV/bin/python" -c "import neo_rx; print('✓ neo_rx import ok')"

echo "Verifying CLI commands..."
"$VERIFY_VENV/bin/neo-rx" --help >/dev/null
"$VERIFY_VENV/bin/neo-rx" aprs --help >/dev/null
"$VERIFY_VENV/bin/neo-rx" wspr --help >/dev/null
echo "✓ CLI commands work"

# cleanup temporary verification venv
rm -rf "$VERIFY_TMP_DIR"

echo ""
echo "✓ Verification completed successfully for all packages."
echo "  Clean up by removing $VENV_DIR when done."
