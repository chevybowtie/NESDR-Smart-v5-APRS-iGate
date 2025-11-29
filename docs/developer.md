Developer & Release Notes

These instructions summarize the common developer workflow for setting up a development environment, building wheels, running smoke tests, and performing releases.

Development setup (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
# Install packages in dependency order
pip install -e ./src/neo_core[dev]
pip install -e ./src/neo_telemetry[dev]
pip install -e ./src/neo_aprs[dev,direwolf]
pip install -e ./src/neo_wspr[dev]
pip install -e .[dev,all]
```

You can also use the helper target in the `Makefile`:

```bash
make setup
```

Smoke tests (verify built wheels)

After running `make release` (or `make build`) the built wheels live under `dist/` and `src/*/dist/`.
To quickly verify the wheels in an isolated environment:

```bash
# from the repo root
rm -rf .venv-smoke
python3 -m venv .venv-smoke
.venv-smoke/bin/pip install --upgrade pip wheel setuptools
# install only the wheels built from this repo
.venv-smoke/bin/pip install --no-deps dist/*.whl src/*/dist/*.whl
# install any runtime deps reported on import
.venv-smoke/bin/pip install tomli_w numpy pyrtlsdr aprslib
# quick import checks
.venv-smoke/bin/python -c "import importlib; importlib.import_module('neo_rx'); print('neo_rx OK')"
# CLI smoke
.venv-smoke/bin/neo-rx --version
```

Release quick reference

The project uses `scripts/release.py` driven by the `Makefile` target `release`.
The common options are:

- `DRY_RUN=1` — simulate the release (default safe action)
- `SKIP=1` — skip the "already at version" guard
- `FORCE=1` — force tag recreation
- `UPLOAD=1` — upload built artifacts to PyPI (requires credentials)

Examples:

```bash
# Dry-run for version 0.2.8
make release VERSION=0.2.8 DRY_RUN=1

# Build and create tags locally (no upload)
make release VERSION=0.2.8 SKIP=1 FORCE=1

# Build, create tags, and upload to PyPI (requires credentials)
make release VERSION=0.2.8 SKIP=1 FORCE=1 UPLOAD=1
```

Safety notes

- Ensure your working tree is clean: `git status --porcelain` should be empty.
- The release script may refuse to run if the requested version equals the repo version — use `SKIP=1` carefully.
- Uploading to PyPI will use `twine` under the hood; do not run with `UPLOAD=1` on a machine without the intended credentials.

Packaging note

During builds you may see a setuptools warning like:

```
Package 'neo_wspr.wspr.bin' is absent from the `packages` configuration
```

This is informational: the `wspr/bin` directory contains a bundled helper binary and is packaged as package data. If you prefer to silence the warning, either include the subpackage explicitly in `pyproject.toml` packages, or change packaging to rely on automatic discovery (`find:`) and/or explicit `package-data` entries.
