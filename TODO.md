## Best Practices & Tooling
* Introduce mypy with `--strict` for key modules (APRS, radio) to catch protocol mismatches early.
* Add `pyproject.toml` `[tool.coverage.run]` configuration for consistent coverage runs (`branch = true`).
* Evaluate asyncio or trio for long-running IO loops instead of threads.

## APRS Client (`aprsis_client.py`)
### Follow-ups
* Add connection lifecycle logging (connect, reconnect, close) at `INFO`/`DEBUG` to aid diagnostics.
* Consider a retry/backoff helper to avoid rapid APRS-IS reconnect loops.

## Config Module (`config.py`)
### Follow-ups
* Decide whether `_xdg_path` should be promoted to a public helper or documented as internal-only.
* `_drop_none` is generic; consider moving it into a shared utilities module.

## Diagnostics Command (`diagnostics.py`)
### Follow-ups
* Expand the `--json` payload with tool version metadata so automated checks can assert expectations.
* Ensure warning and error logs surface in a single summary record to help log aggregation.

## Setup Command (`setup.py`)
### Findings
Extensive user interactivity logic makes unit testing difficult; consider isolating prompt I/O behind interfaces.
### Follow-ups
* Continue expanding automated coverage for additional prompt flows as new requirements emerge.

## Listener Command (`listen.py`)
### Follow-ups
* Review thread and subprocess lifecycle handling to guarantee clean shutdown on signals.
* Add integration coverage for `--once` and `--no-aprsis` to protect CLI defaults.

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


