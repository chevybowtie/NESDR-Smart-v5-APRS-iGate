# Neo-RX

Command-line utility for turning an SDR (for example a NESDR Smart v5 RTL-SDR) into a turn-key receive-only APRS iGate by using an APRS-IS uplink.

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
Install the project in editable mode along with the Direwolf helper extra:
```bash
pip install -e '.[direwolf]'
```
For WSPR support, add the WSPR extra (includes the bundled `wsprd` binary):
```bash
pip install -e '.[direwolf,wspr]'
```
Add `.[dev]` if you also want formatting, linting, and test tooling.

Note about APRS library: the project pins a relaxed constraint for `aprslib` in `pyproject.toml` (for example `aprslib>=0.7.2,<0.9`) because `aprslib>=0.8` is not available on PyPI as of Oct 2025. If you need a newer upstream release, pin to a VCS URL or wait for the official PyPI release. See `DEVELOPER_NOTES.md` for more details.

## 3. Run the interactive setup
Launch the onboarding wizard to capture station details and render the initial configuration:
```bash
neo-rx setup
```
During setup you will be asked for:
- Callsign-SSID and APRS-IS passcode (optionally stored in the system keyring)
- APRS-IS server endpoint
- Station latitude/longitude (optional but recommended)
- Direwolf KISS host/port

The wizard writes `config.toml` to `~/.config/neo-rx/` (override via `NEO_RX_CONFIG_PATH`) and can render `direwolf.conf` plus run a quick hardware validation. Re-run with `--reset` to overwrite an existing config.

To validate an existing configuration without prompts, use the non-interactive mode and point at the file you want to check:
```bash
neo-rx setup --non-interactive --config path/to/config.toml
```
If `--config` is omitted, the command looks for the file at `NEO_RX_CONFIG_PATH` (when set) or in the default config directory.

## 4. Verify the environment (optional)
Use diagnostics to confirm software, SDR, and network reachability:
```bash
neo-rx diagnostics --verbose
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
neo-rx diagnostics --verbose --color

# Disable colors explicitly
neo-rx diagnostics --verbose --no-color

# Disable colors via environment variable
NO_COLOR=1 neo-rx diagnostics --verbose
```

Notes:
- JSON output produced with `--json` is always plain and machine-readable
	(no ANSI color codes are injected).
- When colors are enabled the status labels in the human-readable report are
	marked with ANSI color sequences; these may be visible when capturing
	logs to files, so prefer `--json` for automated tooling or CI.

## 5. Start listening
```bash
neo-rx listen
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

Logs and temporary probe outputs are stored beneath `~/.local/share/neo-rx/logs/` by default.

## 6. WSPR Monitoring (optional)
If you installed WSPR support, you can monitor WSPR bands for propagation reports:
```bash
neo-rx wspr
```

The WSPR monitor will:
1. Cycle through WSPR bands (80m, 40m, 30m, 10m) with 2-minute intervals
2. Capture IQ samples from the RTL-SDR
3. Decode signals using `wsprd`
4. Log spots to JSON-lines and publish to MQTT (if configured)

Useful flags:
- `--calibrate` to measure and apply frequency correction
- `--scan` to scan bands without decoding
- `--upload` to submit queued spots to WSPRnet
- `--config PATH` to point at an alternate configuration file

WSPR data is stored beneath `~/.local/share/neo-rx/wspr/` by default.

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

## Troubleshooting
- `neo-rx diagnostics` surfaces missing dependencies, SDR availability, and network reachability issues.
- Ensure `rtl_fm`, `rtl_test`, `direwolf`, and `sox` (optional) are installed and executable.
- Review Direwolf and listener logs under `~/.local/share/neo-rx/` for detailed errors.
- Re-run `neo-rx setup --reset` if you need to regenerate configuration files or Direwolf templates.

## Onboarding and setup details

For a full specification of the interactive onboarding flow (what `neo-rx setup` does, preconditions, prompts, validation rules, and implementation notes), see the detailed onboarding specification in the docs:

- docs/onboarding-spec.md
