# Developer Notes

## Project Environment
- Primary target is Python 3.11+; CI smoke tests run against 3.11 and 3.13 locally.
- Create a local venv (`python3 -m venv .venv`) and install with `pip install -e '.[direwolf]'` plus `.[dev]` for tooling.
- `NESDR_IGATE_CONFIG_PATH` can override the default config directory for quick iterations.

## Tooling Standards
- Formatting: `ruff format` (PEP 8 style) with 4-space indentation, trailing commas enabled.
- Linting: `ruff check` is the gatekeeper; treat warnings as errors before committing.
- Type checking: `pyright` runs in strict mode for command modules; general modules aim for `--pythonversion 3.11` compliance.
- Git hooks (optional): add pre-commit with `pre-commit install` to run formatting and lint checks automatically.

## Logging and Observability
- All commands use `logging` with module-level loggers; avoid bare `print` outside CLI argument parsing.
- Default log level is `INFO`; honor `--log-level` CLI flag and `NESDR_IGATE_LOG_LEVEL` env override.
- Structured diagnostics live under `~/.local/share/nesdr-igate/logs/`; keep file writes atomic to avoid partial logs.

## CLI and UX Conventions
- CLI entry point is `nesdr-igate`; no arguments defaults to `listen` for quick starts.
- Commander modules follow `Command.run()` taking `ParsedArgs` and returning an exit code (0 success, otherwise failure).
- Comment complex argument parsing with inline notes; use `argparse` subparsers and stick to kebab-case flags (`--log-level`).
- Non-interactive flows must accept `--config PATH` to support testing and automation.

## Configuration Artifacts
- Primary settings live in `config.toml` beneath `~/.config/nesdr-igate/` unless overridden.
- Setup wizard renders `direwolf.conf`; keep templates in sync with Direwolf upstream defaults.
- Secrets such as APRS-IS passcodes are stored via `keyring` when possible; fall back to plaintext only with explicit user opt-in.

## Testing
- Run `.venv-1/bin/python -m pytest --cov` for full coverage reports; cover multi-module interactions by using the `tests/test_listen_command_extended.py` suite.
- Use `pytest caplog` fixtures to assert logging paths rather than string comparisons of stdout.
- Add regression tests for every new CLI flag or config knob; integration fixtures spin up temporary config directories in `/tmp`.
- When hardware dependencies are unavoidable, guard tests with `pytest.mark.slow` to skip in CI.

## Release and Packaging
- Version is managed in `pyproject.toml`; either update the version fields manually or install Hatch (`python -m pip install hatch`) and run `hatch version <level>`.
- Build artifacts with `python -m build` (install the helper first via `python -m pip install build`) and verify `pip install dist/*.whl` inside a clean venv before tagging.
- Update `README.md` quickstart steps whenever CLI defaults or required binaries change.

## Documentation Habits
- Prefer README updates alongside behavioral changes; keep troubleshooting tips user-focused.
- Use `docs/` for deeper architecture notes if functionality grows beyond this summary.

