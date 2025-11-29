# Changelog

All notable changes to this project will be documented in this file.


## [0.2.12] - 2025-11-29

### Fixed
- Updated github workflow integrations job

## [0.2.11] - 2025-11-29

### Fixed
- Updated github workflow integrations job


## [0.2.10] - 2025-11-29

### Added
- Developer & release documentation: `docs/developer.md` and `docs/release_guide.md` with venv setup, smoke-test steps, and Makefile-driven release examples.

### Changed
- Clarified release workflow and `Makefile` flags (`DRY_RUN`, `SKIP`, `FORCE`, `UPLOAD`) in documentation.
- Packaging guidance added to explain the `neo_wspr.wspr.bin` setuptools warning and how to silence it if desired.

### Fixed
- APRS handling: added typing overloads and fixed `_append_q_construct` to preserve correct `str` vs `bytes` behavior and avoid IDE/type-checker complaints.
- NESDR backend: adjusted `RtlSdr` instantiation to use a positional argument and added a targeted `# type: ignore[call-arg]` to reconcile runtime API with type checking.

### Testing
- Recreated development virtual environment and performed editable installs for subpackages in dependency order.
- Ran full local test suite and built wheels for all packages.
- Performed smoke tests by installing the built wheels into an ephemeral venv (`.venv-smoke`) and verified imports and CLI behavior (`neo-rx --version`).

### Release
- Performed a local release build for `0.2.8` (no upload): built sdists/wheels, created tags `neo-core-v0.2.8`, `neo-telemetry-v0.2.8`, `neo-aprs-v0.2.8`, `neo-wspr-v0.2.8`, `neo-rx-v0.2.8`, and pushed branch + tags to `origin`.
- To publish artifacts to PyPI, run the release target with `UPLOAD=1` (ensure credentials are configured and you understand `SKIP`/`FORCE` semantics).

## [0.2.3] - 2025-11-27

### Changed
- Modularization: Completed split into `neo_core`, `neo_aprs`, `neo_wspr`, and `neo_telemetry` with shims for backward compatibility under `neo_rx`.
- CLI version: `neo-rx --version` now reads from local `pyproject.toml` when running from source, ensuring accurate version reporting during development.

### Fixed
- APRS listen tests aligned with q-construct placement in TNC2 frames.
- Diagnostics logging captured via `neo_aprs.commands.diagnostics` for text mode output checks.
- MQTT testability: telemetry shim exposes `time` and `mqtt`; implementation prefers shim-injected namespaces for deterministic tests.
- WSPR uploader JSON: when `--heartbeat` is requested, JSON includes `"heartbeat_sent": true`.
- RTL-SDR compatibility: added lightweight `rtlsdr` stub and `_compat.prepare_rtlsdr()` to avoid external import failures in tests.

### Testing
- All tests pass (228/228) after updating imports to new package layout and adjusting CLI/APRS expectations.

## [0.2.2] - 2025-11-25

### Fixed
- **APRS packet handling**: Fixed critical issue where APRS packets were being re-encoded with UTF-8, which corrupted binary payloads and created modified duplicates. Packets are now treated as raw byte sequences throughout the iGate, preserving original packet content for correct duplicate suppression and loop prevention.
- **APRS-IS packet truncation**: Implemented proper single-line packet truncation at the first CR or LF character in AX.25 info fields, as required by APRS-IS protocol. Prevents embedded newlines from being misinterpreted as commands or separate packets by APRS-IS servers.


### Changed
- `kiss_payload_to_tnc2()` now returns `bytes` instead of `str` to preserve binary packet content. Accepts binary control codes and non-UTF-8 sequences in packet info fields without modification.
- `APRSISClient.send_packet()` now accepts both `str` and `bytes` packets, sending them as-is without UTF-8 re-encoding.

### Testing & Tooling
- Added comprehensive tests for binary packet preservation (non-UTF-8 data in info fields) and CR/LF truncation behavior.

## [0.2.1] - 2025-11-08

### Changed
- The `listen` command now logs a startup banner that includes the packaged version, callsign, and APRS-IS endpoint, making it easy to confirm the running build from captured logs.
- Text-mode diagnostics runs emit a matching `neo-rx aprs diagnostics v…` banner so operators and support logs clearly identify the tool version without switching to JSON output.

### Testing & Tooling
- Extended CLI and diagnostics tests to assert the new version banners so future regressions are caught automatically.
- Bumped the project version to 0.2.1 in `pyproject.toml` to publish the logging enhancements.

## [0.2.0] - 2025-11-01

### Breaking
- Renamed the project and installable package from `nesdr-igate` to `neo-rx`, including the CLI entry point and Python import paths.

### Added
- Added a persistent listener log at `~/.local/share/neo-rx/logs/neo-rx.log` with UTC timestamps while keeping stdout output unchanged.
- While `neo-rx aprs listen` runs, pressing `s` now prints a 24-hour station activity summary that survives restarts by reading the listener log.
- Introduced optional software TOCALL rewriting for APRS-IS uplink traffic to better identify packets originated by the local station.
- Added opt-in colorized output for CLI commands and diagnostics with explicit `--color`/`--no-color` flags and `NO_COLOR` environment support.

### Changed
- Stats lines now include UTC timestamps and prompt operators about the new summary after establishing the APRS-IS connection.
- Centralized version reporting through `neo_rx.__version__` and ensured the CLI writes both to stdout and the persistent log file.

### Fixed
- Improved diagnostics for Direwolf installation and connectivity checks, providing clearer messaging when dependencies are missing or misconfigured.
- Hardened RTL-SDR detection by instantiating devices during diagnostics to catch partially installed drivers.

### Documentation
- Updated README and supporting docs to reflect the new project name, persistent logging, and required system packages (including `python3-venv`).
- Refreshed Direwolf integration and onboarding specifications to align with the current setup flow.

### Testing & Tooling
- Added unit coverage for the listener summary feature and tightened assertions around timestamped stats output.
- Adjusted release and configuration helpers to match the renamed package structure.

## [0.1.2] - 2025-10-27

- Documentation-only release to align version references with 0.1.2 packaging.

## [0.1.1] - 2025-10-26

- Prep release with packaging metadata fixes, dependency pin updates, and release automation scripts.

## [0.1.0] - 2025-10-26

- Initial public release.
