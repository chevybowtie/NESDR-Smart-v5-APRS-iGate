# Neo-RX

Multi-mode command-line utility for turning an SDR (for example a NESDR Smart v5 RTL-SDR) into a turn-key APRS iGate, WSPR monitor, or ADS-B aircraft tracker.

Features:
- **APRS iGate**: Receive-only APRS with APRS-IS uplink via Direwolf
- **WSPR monitoring**: Multi-band propagation tracking with WSPRnet integration
- **ADS-B monitoring**: Aircraft tracking with optional ADS-B Exchange reporting
- **Concurrent operation**: Run APRS, WSPR, and ADS-B simultaneously on different SDRs
- **Config layering**: Multi-file configuration with precedence (defaults < mode < env < CLI)
- **Per-instance isolation**: Independent data/log directories via `--instance-id`
- **Multi-package architecture**: Modular design with separate packages for core, telemetry, APRS, WSPR, and ADS-B functionality

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

## 1. Clone the repo and create a virtual environment
```bash
git clone https://github.com/chevybowtie/NESDR-Smart-v5-APRS-iGate.git
cd NESDR-Smart-v5-APRS-iGate

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

# Core + ADS-B only
pip install neo-adsb

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
pip install -e ./src/neo_adsb[dev]

# Install metapackage CLI
pip install -e .[dev,all]
```

Or use the automated setup:
```bash
make setup
```

### Optional extras
- `direwolf`: Adds `sox` for Direwolf audio helpers (APRS only)
- `adsb`: ADS-B aircraft tracking with ADS-B Exchange integration
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
- `--log-level {debug,info,warning,error}` to control console output verbosity

### Console output and logging

By default, the listener runs at `INFO` log level, which displays:
- Startup messages (version, callsign, server connection)
- Each received frame with port and TNC2 packet preview
- APRS-IS connection status and errors
- Periodic statistics (every 60 seconds)
- Interactive prompts (press `s` for 24-hour summary, `q` to quit)

All console output is simultaneously written to `~/.local/share/neo-rx/logs/aprs/neo-rx.log` (or `~/.local/share/neo-rx/instances/<id>/logs/aprs/neo-rx.log` when using `--instance-id`) with ISO 8601 timestamps.

To reduce console noise while keeping file logs intact, use `--log-level warning` or `--log-level error`. To see detailed debug information (useful for troubleshooting), use `--log-level debug`.

You can also set the log level via the `NEO_RX_LOG_LEVEL` environment variable:
```bash
NEO_RX_LOG_LEVEL=debug neo-rx aprs listen
```


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

## 7. ADS-B Monitoring (optional)

Monitor aircraft traffic using dump1090/readsb with optional ADS-B Exchange reporting:

```bash
neo-rx adsb listen
```

### Prerequisites

ADS-B monitoring requires a decoder daemon that owns the SDR and writes `aircraft.json`:

- `readsb` (recommended)
- `dump1090-fa` or `dump1090` (alternative)

neo-rx reads the JSON these daemons produce; it does not tune the SDR in ADS-B mode.

On Debian/Ubuntu systems (readsb):
```bash
sudo apt install readsb
sudo systemctl enable --now readsb
```
Optionally, install the ADS-B Exchange feeder (handles network reporting):
```bash
curl -L -o /tmp/axfeed.sh https://adsbexchange.com/feed.sh
sudo bash /tmp/axfeed.sh
```
Typical services involved:
```bash
systemctl list-units 'dump1090*' 'readsb*' 'adsbexchange*'
# expect: readsb.service (running), adsbexchange-feed.service (running),
#         adsbexchange-mlat.service (auto-restart if not configured)
```

### ADS-B commands

```bash
# Start ADS-B monitoring
neo-rx adsb listen [--json-path /run/readsb/aircraft.json]

# Run diagnostics
neo-rx adsb diagnostics [--verbose] [--json]

# Interactive setup
neo-rx adsb setup
```

Useful flags:
- `--json-path PATH` to specify decoder JSON location (auto-detects common paths like `/run/readsb/aircraft.json` and `/run/dump1090-fa/aircraft.json`)
- `--poll-interval SECONDS` to set update frequency (default: 1.0)
- `--quiet` to suppress aircraft display output
- `--instance-id NAME` to isolate data/logs for concurrent runs
- `--config PATH` to point at your `config.toml` (ensures MQTT settings load)

Live map
--------

If you installed `tar1090` (commonly bundled with readsb setups), you can view a
live map of local traffic at:

- http://localhost/tar1090/

neo-rx reads from the same decoder backend; the map is independent and provides
a rich browser-based view alongside the terminal table.

### ADS-B Exchange Integration

For feeding data to ADS-B Exchange, install the official feedclient:
```bash
curl -L -o /tmp/axfeed.sh https://adsbexchange.com/feed.sh
sudo bash /tmp/axfeed.sh
```

**Python 3.13/3.12 Users:** The MLAT client requires the `asyncore` module, which was removed in Python 3.12+. After installing the feeder, if the `adsbexchange-mlat` service fails to start, fix the venv:

```bash
# Option 1: Install asyncore backport
sudo /usr/local/share/adsbexchange/venv/bin/pip install pyasyncore
sudo systemctl restart adsbexchange-mlat

# Option 2: Recreate venv with Python 3.11 (if available)
sudo apt install python3.11 python3.11-venv
sudo rm -rf /usr/local/share/adsbexchange/venv
sudo python3.11 -m venv /usr/local/share/adsbexchange/venv
sudo /usr/local/share/adsbexchange/venv/bin/pip install --upgrade pip setuptools wheel
cd /usr/local/share/adsbexchange/mlat-client-git
sudo /usr/local/share/adsbexchange/venv/bin/pip install .
sudo systemctl restart adsbexchange-mlat
```

Verify MLAT is running:
```bash
sudo systemctl status adsbexchange-mlat
neo-rx adsb diagnostics --verbose
```

neo-rx provides status monitoring for ADS-B Exchange services:
```bash
neo-rx adsb diagnostics --verbose
```

This will show:
- dump1090/readsb installation and status
- ADS-B Exchange feedclient installation
- Feed and MLAT service status

Check your feed status:
- https://www.adsbexchange.com/myip
- https://map.adsbexchange.com/mlat-map

ADS-B data is stored beneath `~/.local/share/neo-rx/adsb/` by default.

When MQTT is enabled, ADS-B publishes per-aircraft JSON to `neo_rx/adsb/aircraft`. Verify with:

```bash
mosquitto_sub -h <broker-host> -p 1883 -t 'neo_rx/adsb/aircraft' -v
```

## MQTT Publishing

Neo-RX can publish runtime data to an MQTT broker for dashboarding or downstream processing. Enable and configure MQTT in your main `config.toml` under the `[mqtt]` table. Each mode publishes to a distinct topic by default.

### Configure MQTT (global)

Add the following to your config (used by all modes):

```toml
[mqtt]
enabled = true           # set true to publish
host = "localhost"       # broker host
port = 1883              # broker port
topic = "neo_rx/{mode}"  # optional base topic; modes override
```

If you prefer environment variables, you can also set:

```bash
export NEO_RX_MQTT__ENABLED=true
export NEO_RX_MQTT__HOST=localhost
export NEO_RX_MQTT__PORT=1883
export NEO_RX_MQTT__TOPIC=neo_rx/{mode}
```

### APRS

- Default topic: `neo_rx/aprs/frames`
- Payloads: decoded frame summaries suitable for dashboards (callsign, path, type). Exact content may vary by release.
- Enable via `[mqtt]` config (global). APRS will honor the broker settings and publish when enabled.

Run and subscribe:

```bash
neo-rx aprs listen
mosquitto_sub -h localhost -p 1883 -t 'neo_rx/aprs/frames' -v
```

### WSPR

- Default topic: `neo_rx/wspr/spots`
- Payloads: spot JSON including reporter callsign, grid, frequency, SNR, drift, timestamp.
- When `[wspr].uploader_enabled = true`, publishing continues alongside uploader queueing.

Run and subscribe:

```bash
neo-rx wspr listen
mosquitto_sub -h localhost -p 1883 -t 'neo_rx/wspr/spots' -v
```

### ADS-B

- Default topic: `neo_rx/adsb/aircraft`
- Payloads: per-aircraft JSON with `hex`, `flight`, `altitude_ft`, `latitude`, `longitude`.
- neo-rx reads `aircraft.json` from `readsb`/`dump1090`; publishing does not control the SDR.

Run and subscribe:

```bash
neo-rx adsb listen
mosquitto_sub -h localhost -p 1883 -t 'neo_rx/adsb/aircraft' -v
```

### Notes

- Topics: You can override the default topic via `[mqtt].topic`. Some modes may append a suffix (e.g., `adsb/aircraft`).
- Broker auth/TLS: If your broker requires authentication or TLS, run it behind a local bridge or adapt the telemetry publisher to include credentials (future enhancement).
- Performance: Messages are small and published at the poll cadence (typically 1 Hz). Use per-instance IDs to isolate streams from concurrent runs.

## Concurrent operation

Run APRS, WSPR, and ADS-B simultaneously on different SDRs:

```bash
# Terminal 1: APRS iGate on first SDR
neo-rx aprs listen --device-id 00000001 --instance-id aprs-east

# Terminal 2: WSPR monitor on second SDR
neo-rx wspr listen --device-id 00000002 --instance-id wspr-20m

# Terminal 3: ADS-B monitor on third SDR (via dump1090)
neo-rx adsb listen --instance-id adsb-local
```

Each instance maintains isolated data and log directories:
- APRS: `~/.local/share/neo-rx/instances/aprs-east/aprs/` (data), `~/.local/share/neo-rx/instances/aprs-east/logs/aprs/` (logs)
- WSPR: `~/.local/share/neo-rx/instances/wspr-20m/wspr/` (data), `~/.local/share/neo-rx/instances/wspr-20m/logs/wspr/` (logs)
- ADS-B: `~/.local/share/neo-rx/instances/adsb-local/adsb/` (data), `~/.local/share/neo-rx/instances/adsb-local/logs/adsb/` (logs)

## Troubleshooting
- `neo-rx aprs diagnostics`, `neo-rx wspr diagnostics`, or `neo-rx adsb diagnostics` surfaces missing dependencies, SDR availability, and network reachability issues.
- Ensure `rtl_fm`, `rtl_test`, `direwolf`, and `sox` (optional) are installed and executable.
- Review mode-specific logs under `~/.local/share/neo-rx/logs/{aprs,wspr}/` (or per-instance paths) for detailed errors. If you want on-disk logs to expire automatically, configure host-level rotation (for example a `logrotate` rule with `weekly` + `rotate 4` against `~/.local/share/neo-rx/logs/**/*.log`). See `docs/diagnostics.md` for the sample stanza and systemd notes.
- Re-run `neo-rx aprs setup --reset` or `neo-rx wspr setup --reset` if you need to regenerate configuration files or templates.

## Onboarding and setup details

For a full specification of the interactive onboarding flow (what `neo-rx aprs setup` does, preconditions, prompts, validation rules, and implementation notes), see the detailed onboarding specification in the docs:

- docs/onboarding-spec.md
