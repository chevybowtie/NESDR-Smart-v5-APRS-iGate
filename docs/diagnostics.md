# Diagnostics Command Outline

Defines the behavior of `neo-igate diagnostics`, providing status snapshots for the SDR, Direwolf, and APRS-IS uplink.

## Command Summary
- Usage: `neo-igate diagnostics [--json] [--verbose]`
- Default output: human-readable status table.
- `--json`: emit structured JSON suitable for scripting.
- `--verbose`: include extended details (logs, environment info).

## Checks Performed

### 1. Environment
- Active virtual environment detected?
- Python version and executable path.
- Package versions (`pyrtlsdr`, `aprslib`, `numpy`).

### 2. SDR Hardware
- Enumerate RTL-SDR devices (`pyrtlsdr.RtlSdr.get_device_count`).
- If configured device index is reachable:
  - Tuner info (manufacturer, serial, gain range).
  - Attempt tune to configured frequency and read a short sample buffer.
  - Report signal strength (RSSI estimate) and DC offset metrics (if available).

### 3. Direwolf / KISS
- Check connectivity to KISS host:port.
- Send no-op FEND frame, confirm bytes received.
- If managed Direwolf:
  - Check subprocess status.
  - Tail last N log lines for warnings/errors.
- If external Direwolf:
  - Suggest verifying `direwolf -t 0` output if connection fails.

### 4. APRS-IS Uplink
- Attempt TCP connection to configured APRS-IS server.
- Perform login handshake in `-test` / no-beacon mode (or use keepalive).
- Measure latency (connect and login response time).
- Report number of packets forwarded during current session (if telemetry available).

### 5. Configuration & Paths
- Display config file path, timestamp, and permission bits.
- Keyring status for passcode storage (keyring backend name or fallback warning).
- Location of logs (`~/.local/share/neo-igate/logs`).

## Output Schema
```
SDR:
  status: ok|warning|error
  message: "..."
  device_index: 0
  gain_db: 33.8
  rssi_dbm: -45.3
  sample_rate_sps: 250000

Direwolf:
  status: ok|warning|error
  message: "..."
  kiss_host: "127.0.0.1"
  kiss_port: 8001
  last_packet_ts: "2025-10-25T17:40:22Z"

APRS_IS:
  status: ok|warning|error
  message: "..."
  server: "noam.aprs2.net"
  latency_ms: 120

Config:
  status: ok|warning|error
  path: "/home/user/.config/neo-igate/config.toml"
  updated: "2025-10-25T17:25:00Z"
  permissions: "rw-------"
```

`--json` flag outputs the same information as JSON (camelCase recommended for keys).

## Exit Codes
- `0`: all checks OK or warnings only.
- `1`: one or more critical errors preventing operation (e.g., SDR not detected, Direwolf unreachable, APRS-IS authentication failure).

## Implementation Notes
- Use structured results internally (dataclasses) so both human and JSON output share logic.
- Provide friendly remediation hints when status is warning/error.
- Ensure diagnostics can run without SDR connected by flag `--skip-sdr` (future enhancement).
- Add unit tests for formatting and error mapping.
