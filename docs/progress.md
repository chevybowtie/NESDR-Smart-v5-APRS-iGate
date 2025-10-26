# Project Progress & TODO

## MVP Scope
- Radio front end validation for NESDR V5 (gain, sample rate, signal check around 144.390 MHz)
- Baseband capture pipeline: IQ stream to mono FM audio (≈12 kHz bandwidth)
- Audio processing: low-pass + pre-emphasis + AGC to feed decoder at ~8 ksps
- AX.25/APRS packet decoding via existing libraries or external tools (e.g., direwolf, aprslib)
- APRS-IS iGate client: maintain TCP session, forward decoded packets with station metadata
- CLI `listen` command with configurable callsign/passcode, RF settings, stats display
- Diagnostics and logging (packet counters, optional audio/packet recording)
- Testing strategy: unit tests for parser/uplink, integration test using recorded IQ samples

## User Onboarding
- Prerequisites: rtl-sdr driver install, USB permissions, Python runtime/virtualenv availability
- Hardware check: detect NESDR, validate tuner lock, capture baseline settings (gain/sample rate)
- Identity collection: APRS callsign-SSID, passcode, optional station coordinates/beacon text
- Network setup: choose APRS-IS server(s), test connectivity, store preferences
- Config storage: persist sanitized settings at `~/.config/nesdr-igate/config.toml`; secure secrets via keyring when possible
- Telemetry/logging opt-in: explain data kept under `~/.local/share/nesdr-igate/logs` with rotation policy
- Verification step: run decoder pipeline against canned IQ sample and perform dry-run upload
- Reset path: `nesdr-igate setup --reset` replays onboarding; document env vars for headless override

## Proposed Repository Layout
- `README.md` — high-level project overview and quick-start
- `pyproject.toml` — dependency and tooling configuration for the Python MVP
- `docs/` — planning notes, onboarding guide, architecture sketches (e.g., this file)
- `scripts/` — helper shell scripts for setup, IQ capture, and tooling automation
- `samples/` — canned IQ/audio captures plus decoded packet fixtures for testing
- `src/nesdr_igate/`
	- `__init__.py` — package metadata
	- `cli.py` — entry point wiring subcommands (`listen`, `setup`, `diagnostics`)
	- `config.py` — load/store configuration, keyring integration
	- `radio/` — SDR capture, demod, audio conditioning modules with swappable device drivers
	- `aprs/` — AX.25 framing, APRS parsing, APRS-IS uplink client
	- `telemetry/` — metrics, logging, health reporting
- `tests/` — unit/integration tests with pytest fixtures and regression data
- `.github/` (later) — CI workflows for linting, tests, release packaging
- `Makefile` or `justfile` — convenience targets (`setup`, `test`, `lint`)

## Python Environment Strategy
- Use the built-in `venv` module to create a project-local virtual environment under `.venv/`
- Provide `make setup` (or `just setup`) target that runs `python3 -m venv .venv` and installs dependencies from `pyproject.toml`
- Pin interpreter version with `.python-version` (optional, for pyenv users) and document activation instructions/VS Code integration
- Ensure onboarding flow verifies interpreter availability and guides users through `source .venv/bin/activate`; never touch system-wide site-packages

## APRS Decoding Approach
- Standardize on `direwolf` in KISS TCP mode for AFSK demod + AX.25 framing; it covers everything the MVP requires (and more)
- Python process connects to Direwolf’s KISS port to receive decoded frames and to inject optional outbound beacons
- Provide install guidance and automated health checks (confirm daemon running, validate KISS handshake) before starting capture

## Completed Work
- Repository skeleton scaffolded to match the proposed layout (Oct 25, 2025)
- Runtime and dev dependency set defined in `pyproject.toml` (Oct 25, 2025)
- Onboarding wizard specification drafted in `docs/onboarding.md` (Oct 25, 2025)
- Sample capture script and guide added (Oct 25, 2025)
- Initial NESDR IQ/audio captures recorded and logged (Oct 25, 2025)
- Direwolf integration plan documented in `docs/direwolf-integration.md` (Oct 25, 2025)
- Diagnostics CLI behavior outlined in `docs/diagnostics.md` (Oct 25, 2025)
- Radio abstraction defined and NESDR backend scaffolded (`src/nesdr_igate/radio/`, Oct 25, 2025)
- Direwolf config template and launch script authored (`docs/templates/direwolf.conf`, `scripts/run_direwolf.sh`, Oct 25, 2025)
- CLI command scaffold implemented with placeholders (`src/nesdr_igate/cli.py`, Oct 25, 2025)
- Baseline `setup` command implemented with interactive prompts and config persistence (Oct 25, 2025)
- Diagnostics command implemented with environment/config/SDR checks (Oct 25, 2025)
- Setup wizard now renders/upgrades Direwolf config from template (Oct 25, 2025)
- rtl_fm audio capture wrapper added with tests (`src/nesdr_igate/radio/capture.py`, Oct 25, 2025)
- KISS TCP client implemented with escape handling and tests (`src/nesdr_igate/aprs/kiss_client.py`, Oct 25, 2025)
- AX.25 payload decoder and APRS-IS client implemented with test coverage (Oct 25, 2025)
- `listen` command now pipes rtl_fm audio into Direwolf, displays decoded packets, and forwards to APRS-IS with an opt-out flag (Oct 25, 2025)

## Next Steps
- Add APRS-IS reconnect/backoff strategy and basic throughput logging in `listen`
- Flesh out DSP pipeline plan (filtering, demod staging) atop the radio layer
- Plan enhancements to `setup` (hardware validation, passcode keyring integration)
