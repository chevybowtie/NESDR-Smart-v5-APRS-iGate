## Best Practices & Tooling
* Adopt logging across commands to replace print, enabling log levels and redirection.
* Introduce mypy with --strict for key modules (aprs, radio) to catch protocol mismatches early.
* Add pyproject [tool.coverage.run] config for consistent coverage runs (branch = true).
* Consider asyncio or trio for long-running IO loops instead of threads.

## APRS Client (aprsis_client.py)
### Findings
* Lacks logging when reconnecting; consider injecting logger.

## Config Module (config.py)
### Findings
* _xdg_path should be public? If internal, docstring clarifies use.
* `_drop_none` is generic; could move to utils.

# Diagnostics Command (diagnostics.py)
### Findings
* Uses print for output with ad-hoc formatting; consider rich or logging for structured reports.

## Setup Command (setup.py)
### Findings
Extensive user interactivity logic makes unit testing difficult; consider isolating prompt I/O behind interfaces.
### Recommendations
* Continue expanding automated coverage for additional prompt flows as new requirements emerge.

## Listener Command (listen.py)
### Findings
* print for logging; migrating to logging would permit structured logs.

### Recommendations
* Swap print with logging.getLogger(__name__).

## CLI Layer (cli.py)
### Findings
* Print-style diagnostics remain; aligns with broader logging work once adopted.

### Recommendations
* Swap print with logging.getLogger(__name__) once logging baseline lands.

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

* Medium: Several long, imperative routines (run_listen, _run_hardware_validation) mix I/O, retry logic, and user prompts without decomposition, hindering testing and violating SRP.
