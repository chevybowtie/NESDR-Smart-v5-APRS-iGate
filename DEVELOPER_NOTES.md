# Developer Notes

## Project Environment
- Primary target is Python 3.11+; CI smoke tests run against 3.11 and 3.13 locally.
- Create a local venv (`python3 -m venv .venv`) and install with `pip install -e '.[direwolf]'` plus `.[dev]` for tooling.
- `NEO_RX_CONFIG_PATH` can override the default config directory for quick iterations.

## Tooling Standards
- Formatting: `ruff format` (PEP 8 style) with 4-space indentation, trailing commas enabled.
- Linting: `ruff check` is the gatekeeper; treat warnings as errors before committing.
- Type checking: `pyright` runs in strict mode for command modules; general modules aim for `--pythonversion 3.11` compliance.
- Git hooks (optional): add pre-commit with `pre-commit install` to run formatting and lint checks automatically.

## Logging and Observability
- All commands use `logging` with module-level loggers; avoid bare `print` outside CLI argument parsing.
- Default log level is `INFO`; honor `--log-level` CLI flag and `NEO_RX_LOG_LEVEL` env override.
- Structured diagnostics live under `~/.local/share/neo-rx/logs/`; keep file writes atomic to avoid partial logs.

## CLI and UX Conventions
- CLI entry point is `neo-rx`; an explicit command is required (invoking with no arguments now errors). Use namespaced groups for clarity: `neo-rx aprs listen`, `neo-rx aprs diagnostics`, `neo-rx wspr listen`, `neo-rx wspr upload`. Legacy top-level commands (`listen`, `setup`, `diagnostics`) remain for backward compatibility but are deprecated in documentation.
- Commander modules follow `Command.run()` taking `ParsedArgs` and returning an exit code (0 success, otherwise failure).
- Comment complex argument parsing with inline notes; use `argparse` subparsers and stick to kebab-case flags (`--log-level`).
- Non-interactive flows must accept `--config PATH` to support testing and automation.

## Configuration Artifacts
- Primary settings live in `config.toml` beneath `~/.config/neo-rx/` unless overridden.
- Setup wizard renders `direwolf.conf`; keep templates in sync with Direwolf upstream defaults.
- Secrets such as APRS-IS passcodes are stored via `keyring` when possible; fall back to plaintext only with explicit user opt-in.

## Testing
- Run `.venv-1/bin/python -m pytest --cov` for full coverage reports; cover multi-module interactions by using the `tests/test_listen_command_extended.py` suite.
- Use `pytest caplog` fixtures to assert logging paths rather than string comparisons of stdout.
- Add regression tests for every new CLI flag or config knob; integration fixtures spin up temporary config directories in `/tmp`.
- When hardware dependencies are unavoidable, guard tests with `pytest.mark.slow` to skip in CI.

## Release and Packaging

### Multi-package architecture
- Project is organized into five coordinated packages:
  - `neo-core`: shared utilities, configuration, radio capture
  - `neo-telemetry`: MQTT publishing and on-disk queue
  - `neo-aprs`: APRS protocol, KISS/APRS-IS clients, listen command
  - `neo-wspr`: WSPR decoding, calibration, scan/upload commands
  - `neo-rx`: metapackage CLI entry point, pulls all subpackages
- Each package lives under `src/<package_name>/` with its own `pyproject.toml`
- Versions must stay synchronized across all five packages

### Release workflow

See `docs/release_guide.md` for complete release instructions, including:
- Automatic release via `make release` (recommended)
- Manual step-by-step release process
- Branch management and GitHub PR workflow
- PyPI publishing options

Quick reference:
```bash
# Create release branch
git checkout -b release/x.y.z

# Verify, build, and tag (versions are auto-synced by release script)
make verify-release
make release VERSION=x.y.z

# Push and create PR on GitHub
git push origin release/x.y.z
git push origin --tags
```

### Build system configuration
- All packages use:
  - `build-system.requires = ["setuptools>=69", "build>=1.0"]`
  - `build-system.build-backend = "setuptools.build_meta"`
- Rationale: `setuptools` is widely supported; `build` provides isolated builds matching PyPI behavior
- Each subpackage uses flat layout with explicit `[tool.setuptools]` package mappings

### User installation
- Install metapackage (recommended): `pip install neo-rx`
- Install specific subpackage: `pip install neo-aprs`
- Offline install: `pip install --no-index --find-links dist neo-rx==x.y.z`
- Verify: `neo-rx --version`, `neo-rx aprs diagnostics --json`

### Notes & compatibility
- License format: All packages use SPDX string `"LicenseRef-Proprietary"` (setuptools table format deprecated)
- Subpackage readmes: Removed to silence `twine check` warnings (metapackage includes README.md)
- Transient warnings: Some deps may reference `pkg_resources`; pin `setuptools<81` if problematic
- `aprslib>=0.8` not on PyPI (Nov 2025); relax requirement to `>=0.7.2,<0.9` for compatibility
- `types-keyring` unpublished; use runtime `keyring` package and document typing via `pyright` config

### CI implications
- Run `make verify-release` on merge to main to catch packaging regressions
- Build in isolated environment via `python -m build` to mirror PyPI behavior
- Gate on `setuptools` deprecation warnings to catch breaking changes early

## Documentation Habits
- Prefer README updates alongside behavioral changes; keep troubleshooting tips user-focused.
- Use `docs/` for deeper architecture notes if functionality grows beyond this summary.
