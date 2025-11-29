# Diagnostics Command Outline

Defines the behavior of mode-specific diagnostics commands (`neo-rx aprs diagnostics`, `neo-rx wspr diagnostics`), providing status snapshots for the SDR, mode-specific services, and network connectivity.

## Command Summary
- Usage: 
  - `neo-rx aprs diagnostics [--json] [--verbose]`
  - `neo-rx wspr diagnostics [--json] [--verbose] [--band 20m]`
- Default output: human-readable status table.
- `--json`: emit structured JSON suitable for scripting.
- `--verbose`: include extended details (logs, environment info).
- `--instance-id NAME`: check instance-specific paths and configuration.

## Checks Performed (Common)

### 1. Environment
- Active virtual environment detected?
- Python version and executable path.
- Package versions (`pyrtlsdr`, `aprslib`, `numpy`, etc.).

### 2. SDR Hardware
- Enumerate RTL-SDR devices (`pyrtlsdr.RtlSdr.get_device_count`).
- If configured device index is reachable:
  - Tuner info (manufacturer, serial, gain range).
  - Attempt tune to configured frequency and read a short sample buffer.
  - Report signal strength (RSSI estimate) and DC offset metrics (if available).
- Note: Use `--device-id SERIAL` to check specific SDRs in concurrent setups.

## APRS-Specific Checks

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

## WSPR-Specific Checks

### 3. Decoder Binary
- Verify bundled `wsprd` binary is present and executable.
- Report version information from wsprd.

### 4. Upconverter Detection
- Analyze recent WSPR spots (if available) to detect frequency offsets.
- Report hint: "likely upconverter" or "direct sampling" based on frequency clusters.
- Use `--band BAND` to focus detection on specific band data.

## Configuration & Paths (Both Modes)

### 5. Configuration & Paths
- Display config file path(s):
  - `~/.config/neo-rx/config.toml` (legacy)
  - `~/.config/neo-rx/defaults.toml`, `aprs.toml`, `wspr.toml` (layered)
- Config layering status (which files are present and loaded).
- Keyring status for passcode storage (keyring backend name or fallback warning).
- Location of mode-specific logs:
  - APRS: `~/.local/share/neo-rx/logs/aprs/` (or per-instance)
  - WSPR: `~/.local/share/neo-rx/logs/wspr/` (or per-instance)
- Data directories:
  - APRS: N/A (minimal state)
  - WSPR: `~/.local/share/neo-rx/wspr/` (spots, queue, runs)

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
  path: "/home/user/.config/neo-rx/config.toml"
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

## Log retention
`neo-rx` keeps each logfile open until the CLI exits, so retention is delegated to the host. A user-level `logrotate` stanza meets the weekly/4-week requirement without modifying the Python logging setup:

```conf
~/.local/share/neo-rx/logs/*.log {
  weekly
  rotate 4
  compress
  missingok
  notifempty
  copytruncate
}
```

- Place the rule in `/etc/logrotate.d/neo-rx` (system-wide) or `~/.config/logrotate.d/` when running per-user.
- Keep `copytruncate` unless you restart the `neo-rx` process during rotation; the CLI and helper scripts hold the file descriptor open.
- Add `create 0640 <user> <group>` or `su <user> <group>` if root invokes `logrotate` for files owned by the service user.
- For systemd units, replace `copytruncate` with a `postrotate systemctl --user restart neo-rx-listen.service` block when you prefer clean file handles over truncation.
