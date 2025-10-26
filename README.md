# NESDR APRS iGate (MVP Planning)

Work-in-progress CLI utility for turning a NESDR Smart v5 into a minimal APRS iGate.

## Status
- Planning and scaffolding phase
- Core design notes tracked in `docs/progress.md`

## Planned Components
- SDR capture and demodulation pipeline with device abstraction (`src/nesdr_igate/radio/`)
- APRS/Direwolf integration for decoding and uplink (`src/nesdr_igate/aprs/`)
- CLI entry points for `listen`, `setup`, and diagnostics (`src/nesdr_igate/cli.py`)
- Telemetry and logging utilities (`src/nesdr_igate/telemetry/`)

## Development Setup
- Requires Python 3.11+
- Create venv: `python3 -m venv .venv` then `source .venv/bin/activate`
- Install deps: `pip install -e '.[dev]'` (installs runtime + dev tooling)
- Primary runtime deps: `pyrtlsdr`, `numpy`, `aprslib`, `tomli-w`
- Capture guidance: see `docs/samples.md` and run `scripts/capture_samples.sh`
- Debian prerequisite packages (for NumPy build tooling, etc.):
	`sudo apt install python3-dev build-essential pkg-config`

## Direwolf Integration
- Follow the step-by-step Debian guide in `docs/direwolf-setup-debian.md`
- Render `docs/templates/direwolf.conf` (or run `nesdr-igate setup` once implemented) to populate `~/.config/nesdr-igate/direwolf.conf`
- Launch the audio pipeline + Direwolf via `scripts/run_direwolf.sh` (ensure it is executable)
- Logs are written to `~/.local/share/nesdr-igate/logs/direwolf.log`

## CLI (Work in Progress)
- `python -m nesdr_igate.cli setup` – interactive onboarding; use `--dry-run` to preview without writing, `--non-interactive` to validate an existing config
- Override config location by setting `NESDR_IGATE_CONFIG_PATH=/path/to/config.toml`
- `python -m nesdr_igate.cli diagnostics [--json] [--verbose]` – snapshot of environment, config, SDR, and connectivity health
- `python -m nesdr_igate.cli listen` – launches rtl_fm → Direwolf audio pipeline, displays decoded packets, and forwards them to APRS-IS (requires rendered `direwolf.conf`, Direwolf in PATH, and valid APRS-IS credentials)
	- Use `--no-aprsis` to run in receive-only mode without touching APRS-IS

## Troubleshooting Tips
- Verify the dongle is hearing RF by piping audio to PulseAudio speakers:
	`rtl_fm -f 144390000 -M fm -s 22050 -g 35 -E deemp -A fast -F 9 | paplay --raw --rate=22050 --channels=1 --format=s16le --`
	Adjust gain (`-g`) or center frequency slightly if APRS tones sound weak.
- Use `rtl_test -p` to measure your dongle's PPM error and update the config (`ppm_correction`) so rtl_fm and the CLI stay on frequency.
- If the CLI isn't decoding your handheld, double-check the handheld is transmitting right on 144.390 MHz; small offsets are enough to confuse Direwolf.
