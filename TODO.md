## Best Practices & Tooling
* Introduce mypy with `--strict` for key modules (APRS, radio) to catch protocol mismatches early.
* Add `pyproject.toml` `[tool.coverage.run]` configuration for consistent coverage runs (`branch = true`).
* Evaluate asyncio or trio for long-running IO loops instead of threads.

## Config Module (`config.py`)
### Follow-ups
* Decide whether `_xdg_path` should be promoted to a public helper or documented as internal-only.
* `_drop_none` is generic; consider moving it into a shared utilities module.

## Setup Command (`setup.py`)
### Findings
Extensive user interactivity logic makes unit testing difficult; consider isolating prompt I/O behind interfaces.
### Follow-ups
* Continue expanding automated coverage for additional prompt flows as new requirements emerge.

## Dependency Modernization (`pyproject.toml`)
Recommendations
* Update stanza:
```
numpy = ">=2.0,<3"
pyrtlsdr = ">=0.3.0,<0.4"
aprslib = ">=0.8.0,<0.9"
tomli-w = ">=1.1,<2"
pytest = ">=8.3"
pytest-asyncio = ">=0.23"  # keep if still needed, else drop
```
* Add dev extras: mypy, black, types-keyring, pytest-rerunfailures, coverage[toml].
* Switch build-system requirements to `["setuptools>=69", "build>=1.0"]` and consider hatchling/pdm/uv for reproducible builds.
* Document runtime optional extras (`[project.optional-dependencies]`) for Direwolf integration vs. headless operation.


