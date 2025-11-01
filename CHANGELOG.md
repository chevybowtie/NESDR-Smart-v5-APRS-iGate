# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

- No unreleased changes yet.

## [0.2.0] - 2025-11-01

### Breaking
- Renamed the project and installable package from `nesdr-igate` to `neo-igate`, including the CLI entry point and Python import paths.

### Added
- Added a persistent listener log at `~/.local/share/neo-igate/logs/neo-igate.log` with UTC timestamps while keeping stdout output unchanged.
- While `neo-igate listen` runs, pressing `s` now prints a 24-hour station activity summary overlay that survives restarts by reading the listener log.
- Introduced optional software TOCALL rewriting for APRS-IS uplink traffic to better identify packets originated by the local station.
- Added opt-in colorized output for CLI commands and diagnostics with explicit `--color`/`--no-color` flags and `NO_COLOR` environment support.

### Changed
- Stats lines now include UTC timestamps and prompt operators about the new summary overlay after establishing the APRS-IS connection.
- Centralized version reporting through `neo_igate.__version__` and ensured the CLI writes both to stdout and the persistent log file.

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
