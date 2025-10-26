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

### Build system & release guidance

- Recommended `build-system` for `pyproject.toml` (this project):
	- `requires = ["setuptools>=69", "build>=1.0"]`
	- `build-backend = "setuptools.build_meta"`

- Why this choice:
	- `setuptools` is the widest-supported build backend and works well with our current code and packaging layout (src/ layout, package-data, entry points).
	- `build` is a small, well-maintained wrapper to produce sdist and wheel in isolated environments.

- Actionable practices:
	- Create a clean ephemeral venv for release verification:

		```bash
		python3 -m venv .venv-release
		.venv-release/bin/pip install --upgrade pip
		.venv-release/bin/pip install -e '.[direwolf]' '.[dev]'
		.venv-release/bin/python -m build
		.venv-release/bin/pip install dist/*.whl
		```

	- Use the included `scripts/verify_release.sh` helper which automates the above steps in a repeatable way.

- Notes & compatibility concerns:
	- Setuptools deprecation: `project.license` as a TOML table is deprecated in newer setuptools; switch to an SPDX string (for example `license = { text = "MIT" }` -> `license = "MIT"` or `license-files`) before 2026-Feb-18 to avoid future build breaks. The verification build will emit a deprecation warning until this is changed.
	- Transient warning: some runtime dependencies (notably `pyrtlsdr` / `rtlsdr`) may emit runtime warnings referencing `pkg_resources` from `setuptools`. If these warnings are problematic, two options exist:
		- Pin `setuptools` to a safe version in CI/build environments (for example `setuptools<81`) until transitive deps remove `pkg_resources` usage.
		- Upgrade or replace the transitive dependency if a newer release removes the `pkg_resources` usage.

- Alternatives to consider (longer-term):
	- `hatchling` (via `hatchling`/`hatch`) offers a modern, fast build backend with simpler configuration for some workflows; migrating requires updating CI and developer docs.
	- `pdm` provides an opinionated workflow with dependency resolution through PEP 621 + PEP 517 but may be heavier to adopt for contributors.

- CI implications:
	- Keep the project's CI build step to run `python -m build` inside an isolated environment (this mirrors how PyPI builds packages) and to run the `scripts/verify_release.sh` on merge to main.
	- Consider adding a lightweight gate that checks for `setuptools` deprecation warnings and fails only on new severe errors (so we catch regressions early without being brittle).

## Documentation Habits
- Prefer README updates alongside behavioral changes; keep troubleshooting tips user-focused.
- Use `docs/` for deeper architecture notes if functionality grows beyond this summary.

