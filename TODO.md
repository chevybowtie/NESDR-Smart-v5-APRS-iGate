## Best Practices & Tooling
* Adopt logging across commands to replace print, enabling log levels and redirection.
* Introduce mypy with --strict for key modules (aprs, radio) to catch protocol mismatches early.
* Add pyproject [tool.coverage.run] config for consistent coverage runs (branch = true).
* Consider asyncio or trio for long-running IO loops instead of threads.

## KISS Client (kiss_client.py)
### Findings
Best Practices
* Replace magic numbers with enums for KISS commands.

## APRS Client (aprsis_client.py)
### Findings
* Lacks logging when reconnecting; consider injecting logger.
* connect quietly returns when already connected; docstring should note idempotence.

## Config Module (config.py)
### Findings
* _xdg_path should be public? If internal, docstring clarifies use.
* Consider `pathlib.Path` for file operations (already used), but `save_config` should use `pathlib.Path`.write_text within a context manager for atomic writes (tempfile).
* `_drop_none` is generic; could move to utils.

# Diagnostics Command (diagnostics.py)
### Findings
* Uses print for output with ad-hoc formatting; consider rich or logging for structured reports.
* _check_sdr handles ImportError but not partially installed pyrtlsdr (raises RuntimeError); cross-check.

## Setup Command (setup.py)
### Findings
* `_run_non_interactive` duplicates load logic already in `_load_existing`.
Extensive user interactivity logic makes unit testing difficult; consider isolating prompt I/O behind interfaces.
### Recommendations
* Factor prompt utilities into separate module with injectable input/output streams for tests.
* Use pathlib.Path.unlink(missing_ok=True) (Python 3.11+) instead of exists + unlink.




## Listener Command (listen.py)
### Findings
* run_listen (~200 lines) mixes config resolution, process orchestration, retries, stats, and signal handling.
* _handle_sigint overrides global handler without restoring on early returns.
* print for logging; migrating to logging would permit structured logs.
* _report_audio_error pollutes STDOUT; consider raising to caller for structured handling.

### Recommendations
* Split `run_listen` into composable helpers (_prepare_radio, _spawn_direwolf, _run_main_loop).
* Refactor to use contextlib.ExitStack for capture/client lifecycle.
* Swap print with logging.getLogger(__name__).


## CLI Layer (cli.py)
### Findings
* `subparsers = parser.add_subparsers(... required=False)` allows empty command; consider default to `listen`.
* `CommandHandler` lacks `Protocol`; adoption improves static typing.

### Recommendations
* Use typing.Protocol for handlers and centralize registration logic.
* Replace print_help branch with parser.set_defaults to reduce conditional.

## Dependency Modernization (pyproject.toml)

Recommendations
 * Update stanza:
```
numpy = ">=2.0,<3"
pyrtlsdr = ">=0.3.0,<0.4"
aprslib = ">=0.8.0,<0.9"
tomli-w = ">=1.1,<2"
pytest = ">=8.3"
pytest-asyncio = ">=0.23"  # keep if still needed, else drop
```

* Add dev extras: mypy, black, types-keyring, pytest-rerunfailures, coverage[toml].
* Switch build-system requirements to ["setuptools>=69", "build>=1.0"] and adopt hatchling/pdm or uv for reproducible builds.
* Document runtime optional extras ([project.optional-dependencies]) for Direwolf integration vs. headless operation.



## Audit Summary

* High: pyproject.toml pins pre-2024 releases (numpy<2, pytest<8) and omits publish-time metadata; upgrade paths needed for Python 3.11+ support and security posture.
* Medium: Several long, imperative routines (run_listen, _run_hardware_validation) mix I/O, retry logic, and user prompts without decomposition, hindering testing and violating SRP.
* Low: APRSISClient and KISSClient expose file-like sockets but do not use context managers/logging best practices and rely on manual print, limiting observability.
* Low: APRSISClient and KISSClient expose file-like sockets but do not use context managers/logging best practices and rely on manual print, limiting observability.