## Future Features & Configuration Options

### WSPR Features
* **Auto-upload to WSPRnet**: Implement `wspr_auto_upload` config option to automatically upload decoded spots to WSPRnet database
* **WSPR spot metadata**: Include station location (`latitude`, `longitude`, `altitude_m`) in spot data when available

### APRS Transmit Features  
* **APRS beaconing**: Implement transmit functionality using `beacon_comment` and `software_tocall` config options
* **Position reports**: Include configured location data in APRS packets

### Configuration Options (Defined but Not Yet Used)
* `altitude_m`: Station altitude for APRS/WSPR metadata
* `beacon_comment`: APRS beacon comment text  
* `software_tocall`: APRS software identifier
* `wspr_auto_upload`: Automatic WSPRnet upload flag

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
Recommendations
* Update stanza (example):
```
numpy = ">=2.0,<3"
pyrtlsdr = ">=0.3.0,<0.4"
aprslib = ">=0.7.2,<0.9"  # relaxed because aprslib>=0.8 is not available on PyPI as of Oct 2025
tomli-w = ">=1.1,<2"
pytest = ">=8.3"
pytest-asyncio = ">=0.23"  # keep if still needed, else drop
```
* Add dev extras: mypy, black/ruff, pytest-rerunfailures, coverage[toml].
	- Note: `types-keyring` is not published on PyPI; do not include it in dev extras. Use `keyring` at runtime for secure passcode storage and document typing/stub strategies separately.
* Switch build-system requirements to `["setuptools>=69", "build>=1.0"]` and consider hatchling/pdm for reproducible builds.
* Document runtime optional extras (`[project.optional-dependencies]`) for Direwolf integration vs. headless operation.


