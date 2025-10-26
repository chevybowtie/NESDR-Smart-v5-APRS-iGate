# NESDR APRS iGate Quickstart

Step-by-step guide to install the CLI, capture a minimal configuration, and start forwarding APRS packets with a NESDR Smart v5.

## 1. Prerequisites
- **Hardware**: NESDR Smart v5 (or compatible RTL-SDR) and access to the 144.390 MHz APRS channel.
- **Operating system**: Linux (Debian/Ubuntu tested).
- **Python**: 3.11 or 3.12. Install the `python3-venv` package if it is missing.
- **System packages**:
	```bash
	sudo apt update
	sudo apt install python3-dev python3-venv build-essential pkg-config rtl-sdr sox direwolf
	```
	Direwolf is required for packet decoding; `sox` is optional but useful for diagnostics.

## 2. Create a Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 3. Install the Project
Install runtime + development tooling along with Direwolf helpers:
```bash
pip install -e '.[dev,direwolf]'
```
Key Python dependencies installed by this command:
- `numpy>=2`
- `pyrtlsdr>=0.3`
- `aprslib>=0.7.2`
- `tomli-w>=1.1`

## 4. Configure the Station
Run the interactive setup wizard to collect station credentials and SDR preferences:
```bash
nesdr-igate setup
```
- Answers are written to `~/.config/nesdr-igate/config.toml`.
- Use `--non-interactive` to validate an existing config or `--dry-run` to preview changes.
- The wizard can also render a Direwolf configuration under `~/.config/nesdr-igate/direwolf.conf`.

## 5. Verify the Environment
Capture a quick health report before listening:
```bash
nesdr-igate diagnostics --verbose
```
This checks Python dependencies, configuration validity, SDR availability, and network reachability.

## 6. Start Listening
Launch the end-to-end pipeline:
```bash
nesdr-igate listen
```
- Defaults connect to Direwolf over KISS TCP and forward frames to APRS-IS using the stored credentials.
- Run with `--no-aprsis` for receive-only mode.
- Press `Ctrl+C` to stop; logs and packet summaries stay in the terminal for now.

## 7. Next Steps
- Review `TODO.md` for planned enhancements (logging, async pipeline, etc.).
- Explore `docs/` for deeper architecture and Direwolf integration notes.
- Use `pip install -e .` without extras only if you plan to run setup/diagnostics without live decoding (Direwolf remains required for `listen`).

## Planned Components
- SDR capture and demodulation pipeline with device abstraction (`src/nesdr_igate/radio/`)
- APRS/Direwolf integration for decoding and uplink (`src/nesdr_igate/aprs/`)
- CLI entry points for `listen`, `setup`, and diagnostics (`src/nesdr_igate/cli.py`)
- Telemetry and logging utilities (`src/nesdr_igate/telemetry/`)

## Direwolf Integration
- Follow the step-by-step Debian guide in `docs/direwolf-setup-debian.md`
- Render `docs/templates/direwolf.conf` (or run `nesdr-igate setup` once implemented) to populate `~/.config/nesdr-igate/direwolf.conf`
- Launch the audio pipeline + Direwolf via `scripts/run_direwolf.sh` (ensure it is executable)
- Logs are written to `~/.local/share/nesdr-igate/logs/direwolf.log`
