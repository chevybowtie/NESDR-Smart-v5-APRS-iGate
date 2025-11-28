# Neo-RX

Multi-mode command-line utility for turning an SDR (for example a NESDR Smart v5 RTL-SDR) into a turn-key APRS iGate or WSPR monitor.

Features:
- **APRS iGate**: Receive-only APRS with APRS-IS uplink via Direwolf
- **WSPR monitoring**: Multi-band propagation tracking with WSPRnet integration
- **Concurrent operation**: Run APRS and WSPR simultaneously on different SDRs
- **Config layering**: Multi-file configuration with precedence (defaults < mode < env < CLI)
- **Per-instance isolation**: Independent data/log directories via `--instance-id`
- **Multi-package architecture**: Modular design with separate packages for core, telemetry, APRS, and WSPR functionality

## Prerequisites
- Linux host with Python 3.11 or newer
- NESDR Smart v5 (or compatible RTL-SDR)
- Direwolf packet modem installed and on `PATH`
	- `rtl_fm`, `rtl_test`, and `direwolf` binaries must be callable
- (Optional) `sox` for Direwolf audio tooling (installed automatically with the `direwolf` extra)
- (Optional) WSPR decoding (bundled with the `wspr` extra)

On Debian- or Ubuntu-based systems you can install the radio tools and Direwolf with:
```bash
sudo apt install rtl-sdr direwolf python3-venv
```
Add `sox` if you want the optional audio helpers:
```bash
sudo apt install sox
```

### WSPR Support
WSPR decoding is supported via the bundled `wsprd` binary (from WSJT-X). No additional installation is required beyond the Python dependencies.

The WSPR feature uses the bundled `wsprd` for IQ data decoding.

## 1. Create and activate a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 2. Install project dependencies

### For end users (from PyPI or local wheels)
Install the `neo-rx` metapackage, which pulls in all subpackages:
```bash
pip install neo-rx
```

To install specific functionality only:
```bash
# Core + APRS only
pip install neo-aprs

# Core + WSPR only
pip install neo-wspr

# Core + telemetry (MQTT publishing)
pip install neo-telemetry
```

### For developers (editable install from source)
Install in dependency order for development:
```bash
# Install core package first
pip install -e ./src/neo_core[dev]

# Install feature packages
pip install -e ./src/neo_telemetry[dev]
pip install -e ./src/neo_aprs[dev,direwolf]
pip install -e ./src/neo_wspr[dev]

# Install metapackage CLI
pip install -e .[dev,all]
```

Or use the automated setup:
```bash
make setup
```

### Optional extras
- `direwolf`: Adds `sox` for Direwolf audio helpers (APRS only)
- `dev`: Formatting, linting, and test tooling
- `all`: All optional dependencies for full functionality

Note about APRS library: the project pins a relaxed constraint for `aprslib` in `pyproject.toml` (for example `aprslib>=0.7.2,<0.9`) because `aprslib>=0.8` is not available on PyPI as of Oct 2025. If you need a newer upstream release, pin to a VCS URL or wait for the official PyPI release. See `DEVELOPER_NOTES.md` for more details.

## 3. Run the interactive setup

Launch the onboarding wizard to capture station details and render the initial configuration:
```bash
# APRS setup
neo-rx aprs setup

# WSPR setup (if you need WSPR-specific configuration)
neo-rx wspr setup
```

During setup you will be asked for:
- Callsign-SSID and APRS-IS passcode (optionally stored in the system keyring)
- APRS-IS server endpoint
- Station latitude/longitude (optional but recommended)
- Direwolf KISS host/port
- WSPR reporter grid and power (for WSPR mode)

The wizard writes `config.toml` to `~/.config/neo-rx/` (override via `NEO_RX_CONFIG_PATH`) and can render `direwolf.conf` plus run a quick hardware validation. Re-run with `--reset` to overwrite an existing config.

### Configuration layering

Neo-RX supports multi-file configuration with precedence:
1. `~/.config/neo-rx/defaults.toml` - Shared defaults
2. `~/.config/neo-rx/aprs.toml` or `~/.config/neo-rx/wspr.toml` - Mode-specific overrides
3. Environment variables (e.g., `NEO_RX_APRS__SERVER=localhost`)
4. CLI flags (e.g., `--config`, `--data-dir`, `--instance-id`)

To validate an existing configuration without prompts, use the non-interactive mode:
```bash
neo-rx aprs setup --non-interactive --config path/to/config.toml
```

## 4. Verify the environment (optional)
Use diagnostics to confirm software, SDR, and network reachability:
```bash
# APRS diagnostics
neo-rx aprs diagnostics --verbose

# WSPR diagnostics
neo-rx wspr diagnostics --verbose
```
Add `--json` for machine-readable output.

Colorized output
----------------

The textual diagnostics output can optionally be colorized for interactive
terminals so status tokens (OK / WARNING / ERROR) are easier to scan:

- `--color` forces colorized output (even when stdout is not a TTY)
- `--no-color` disables colorized output
- The runtime also respects the `NO_COLOR` environment variable as a
	conventional opt-out.

Examples:

```bash
# Force colorized output
neo-rx aprs diagnostics --verbose --color

# Disable colors explicitly
neo-rx wspr diagnostics --verbose --no-color

# Disable colors via environment variable
NO_COLOR=1 neo-rx aprs diagnostics --verbose
```

Notes:
- JSON output produced with `--json` is always plain and machine-readable
	(no ANSI color codes are injected).
- When colors are enabled the status labels in the human-readable report are
	marked with ANSI color sequences; these may be visible when capturing
	logs to files, so prefer `--json` for automated tooling or CI.

## 5. Start listening
```bash
neo-rx aprs listen
```

The listener will:
1. Launch `rtl_fm` and pipe audio into Direwolf
2. Read KISS frames from Direwolf
3. Decode AX.25 payloads for console display
4. Forward packets to APRS-IS using the configured credentials

Useful flags:
- `--no-aprsis` to operate receive-only without APRS-IS uplink
- `--once` to process a single frame batch (helpful for smoke tests)
- `--config PATH` to point at an alternate configuration file
- `--instance-id NAME` to isolate data/logs for concurrent runs
- `--device-id SERIAL` to select a specific RTL-SDR device

Logs and probe outputs are stored beneath `~/.local/share/neo-rx/logs/aprs/` by default (or `~/.local/share/neo-rx/instances/<id>/logs/aprs/` when using `--instance-id`).

## 6. WSPR Monitoring (optional)
If you installed WSPR support, you can monitor WSPR bands for propagation reports:
```bash
neo-rx wspr listen
```

The WSPR monitor will:
1. Cycle through WSPR bands (80m, 40m, 20m, 30m, 10m, 6m, 2m, 70cm) with 2-minute intervals
2. Capture IQ samples from the RTL-SDR
3. Decode signals using `wsprd`
4. Log spots to JSON-lines and publish to MQTT (if configured)
5. Enrich spots with reporter metadata and enqueue them for upload when `[wspr].uploader_enabled = true`

### WSPR commands

```bash
# Start WSPR monitoring listener
neo-rx wspr listen [--band 20m] [--instance-id wspr-1]

# Multi-band scan
neo-rx wspr scan

# Calibrate frequency correction
neo-rx wspr calibrate [--samples path/to/iq.wav]

# Upload queued spots to WSPRnet
neo-rx wspr upload [--heartbeat] [--json]

# WSPR diagnostics (upconverter detection)
neo-rx wspr diagnostics [--band 20m]
```

Useful flags:
- `--band {80m,40m,30m,20m,10m,6m,2m,70cm}` to monitor a single band
- `--instance-id NAME` to isolate data/logs for concurrent runs
- `--device-id SERIAL` to select a specific RTL-SDR device
- `--config PATH` to point at an alternate configuration file

WSPR data is stored beneath `~/.local/share/neo-rx/wspr/` by default (or `~/.local/share/neo-rx/instances/<id>/wspr/` when using `--instance-id`). Each listen run creates a timestamped or instance-labeled directory under `wspr/runs/` for spots and upload queue.

### WSPR uploader configuration

The uploader reuses the main `config.toml`. Add the following keys under the `[wspr]` table to describe your reporter:

```toml
[wspr]
grid = "EM12ab"          # Maidenhead grid (6 characters recommended)
power_dbm = 37            # Reported transmit power in dBm (37 ≈ 5 W)
uploader_enabled = false  # Flip to true to allow `neo-rx wspr --upload`
```

- `grid` is required by WSPRnet. You can enter it manually or derive it from your lat/long via any Maidenhead converter.
- `power_dbm` defaults to 37 if omitted. Set it to the nearest whole-dBm value for your transmit chain.
- `uploader_enabled` is a safety gate: once the uploader logic is wired up, this flag must be `true` before the CLI contacts WSPRnet. Keep it `false` while you verify credentials and networking.

These fields complement existing options such as `wspr_enabled`, `wspr_auto_upload`, and `wspr_bands_hz`.

When `uploader_enabled = true`, `neo-rx wspr` will also start writing an enriched upload queue to `~/.local/share/neo-rx/wspr/wspr_upload_queue.jsonl`. Each record now captures the tuned band (`dial_freq_hz`), the aligned 2-minute slot start, and your reporter metadata (`callsign`, `grid`, `power_dbm`) so subsequent `neo-rx wspr --upload` runs have everything needed to talk to WSPRnet.

`neo-rx wspr upload --json` drains the queue and reports `attempted`, `succeeded`,
`failed`, and a `last_error` string so automation can react to stalled queues.
Each upload uses the rtlsdr-wsprd HTTPS GET contract (same params as `function=wspr`).
Pair it with `--heartbeat` to emit a `wsprstat` ping whenever a drain cycle
produces no successful uploads.

Uploader logs live under `~/.local/share/neo-rx/logs/wspr/` (or per-instance when using `--instance-id`); set
`NEO_RX_LOG_LEVEL=DEBUG` to watch each attempt/heartbeat in real time, and see
`docs/wspr.md` for rate-limit and troubleshooting guidance.

> **Safety gate:** `neo-rx wspr upload` refuses to contact WSPRnet unless `[wspr].uploader_enabled = true`, preventing accidental network submissions.

## Concurrent operation

Run APRS and WSPR simultaneously on different SDRs:

```bash
# Terminal 1: APRS iGate on first SDR
neo-rx aprs listen --device-id 00000001 --instance-id aprs-east

# Terminal 2: WSPR monitor on second SDR
neo-rx wspr listen --device-id 00000002 --instance-id wspr-20m
```

Each instance maintains isolated data and log directories:
- APRS: `~/.local/share/neo-rx/instances/aprs-east/aprs/` (data), `~/.local/share/neo-rx/instances/aprs-east/logs/aprs/` (logs)
- WSPR: `~/.local/share/neo-rx/instances/wspr-20m/wspr/` (data), `~/.local/share/neo-rx/instances/wspr-20m/logs/wspr/` (logs)

## Troubleshooting
- `neo-rx aprs diagnostics` or `neo-rx wspr diagnostics` surfaces missing dependencies, SDR availability, and network reachability issues.
- Ensure `rtl_fm`, `rtl_test`, `direwolf`, and `sox` (optional) are installed and executable.
- Review mode-specific logs under `~/.local/share/neo-rx/logs/{aprs,wspr}/` (or per-instance paths) for detailed errors. If you want on-disk logs to expire automatically, configure host-level rotation (for example a `logrotate` rule with `weekly` + `rotate 4` against `~/.local/share/neo-rx/logs/**/*.log`). See `docs/diagnostics.md` for the sample stanza and systemd notes.
- Re-run `neo-rx aprs setup --reset` or `neo-rx wspr setup --reset` if you need to regenerate configuration files or templates.

## Onboarding and setup details

For a full specification of the interactive onboarding flow (what `neo-rx setup` does, preconditions, prompts, validation rules, and implementation notes), see the detailed onboarding specification in the docs:

- docs/onboarding-spec.md
