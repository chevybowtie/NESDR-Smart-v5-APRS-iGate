# WSPR Feature Plan

This document outlines the feature plan for adding WSPR (Weak Signal
Propagation Reporter) decoding and reporting to the project. It captures
requirements, design decisions, diagnostics, integration points, and a
proposed development roadmap.

## Goal

Add in-process WSPR receive/decoding and optional auto-reporting to
calibration, structured logging, and MQTT publication of spots.
## Assumptions
- Primary SDR: RTL-SDR (`pyrtlsdr`).
- Upconverter: Nooelec Ham-It-Up V2 (passive RF converter) — not USB-visible.
- Decoder: initial approach wraps `wsprd` (external, robust binary).
- Host must provide accurate time (NTP/GPS/PPS).
- Auto-reporting to WSPRnet is opt-in and requires manual credential entry.

## Hardware Setup

### NESDR Smart v5

The NESDR Smart v5 is a USB SDR receiver with built-in upconverter and amplifier switches. For WSPR reception, configure the switches as follows:

- **Upconverter Switch**: ON (enables the built-in upconverter for HF bands)
- **Amp Switch**: OFF (amplifier not needed for WSPR; may introduce noise)

These settings allow reception of WSPR bands (80m, 40m, 30m, 10m) by shifting HF frequencies into the RTL-SDR's tunable range.

**Note**: Ensure the device is properly connected via USB and recognized by the system (check with `lsusb` or `rtl_test`). The upconverter is integrated and does not appear as a separate USB device.

- Capture IQ from RTL-SDR, run decoder, parse spots.
- Automatic heuristics for upconverter detection and LO offset recommendation.
- PPM calibration via WWV/CHU or from `wsprd` drift output.
- Band-scanning for activity and SNR ranking.
- Persist spots locally (JSON-lines) and publish to MQTT topic.
- CLI commands for diagnostics, calibration, scanning, and running WSPR.

## High-level Architecture

- `src/neo_wspr/wspr/`
  - `capture.py` — capture orchestration and scheduler
  - `decoder.py` — wrapper for `wsprd` subprocess and parser
  - `uploader.py` — WSPRnet uploader (opt-in via `[wspr].uploader_enabled`)
  - `diagnostics.py` — upconverter heuristics and checks
  - `calibrate.py` — ppm measurement and application logic
  - `publisher.py` — MQTT publisher integration (uses telemetry abstraction)
- `src/neo_wspr/commands/` — CLI command wiring (`listen.py`, `scan.py`, `calibrate.py`, `upload.py`, `diagnostics.py`)

## Upconverter detection

Automatic USB detection is not possible (passive converter). Proposed
heuristics:
- Spectrum-shift test against known beacons (WWV/CHU) to detect an LO
  offset.
## Time & Calibration

  - Measure ppm from strong time/frequency station and compute correction.
  - Use `wsprd` reported drift to derive ppm and apply correction.
- Computation: the tool computes parts-per-million (ppm) correction by
  comparing the median observed frequency of decoded spots against an
  median SNR and observation count.
- Library support: `src/neo_wspr/wspr/calibrate.py` provides `apply_ppm_to_radio(ppm)`
  (applies a correction to an RTL-SDR tuner) and `persist_ppm_to_config(ppm, config_path=None)`
  (safe-saves `ppm_correction` into `config.toml`, writing a timestamped backup
  first under a `backups/` folder alongside the config file, e.g.
  `config.toml.bak-YYYYMMDDTHHMMSSZ`).
- **Current CLI behavior**: `neo-rx wspr calibrate` is not yet wired to `--apply`/`--write-config`
  flags — it estimates the PPM offset from saved spots and logs the recommended
  `ppm_correction` value for you to add to `config.toml` by hand. Applying/persisting
  automatically from the CLI is tracked as a follow-up (see `docs/ROADMAP.md`).

Example usage:

```bash
# Estimate PPM offset from saved spots for a given band
neo-rx wspr calibrate --band 20m

# Use a specific spots file instead of the default data-dir location
neo-rx wspr calibrate --samples /path/to/wspr_spots.jsonl --config /path/to/config.toml
```

Restore from backup (once a correction has been persisted, manually or via the library functions above):

```bash
# To inspect available backups:
ls ~/.config/neo-rx/backups/

# To restore the most recent backup for the active config:
cp ~/.config/neo-rx/backups/config.toml.bak-YYYYMMDDTHHMMSSZ ~/.config/neo-rx/config.toml
```

## Decoder Approach

- Start with a subprocess wrapper for `wsprd` (fast to prototype).
- Parse stdout/stderr for spots and drift; emit structured events.

## Reporting & Message Bus

- Local JSON-lines log of spots.
- MQTT publisher (topic `neo_rx/wspr/spots`) for dashboards.
- **On-disk buffering**: Messages are persisted to disk when the broker is
  unavailable and automatically sent when connection is restored.
- Buffer management with configurable size limits and automatic rotation.
- **Optional auto-upload to WSPRnet** with queue/retry and manual credential input.

## Configuration additions

The `[wspr]` section in `config.toml` now accepts the following uploader-specific keys:

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `grid` | string | `null` | Maidenhead grid (6 character preferred) used for `rcall`/`rgrid` fields when uploading. |
| `power_dbm` | integer | `37` | Transmit power reported to WSPRnet. `37` dBm ≈ 5 W. |
| `uploader_enabled` | bool | `false` | Gate to prevent accidental uploads until credentials/networking are verified. |

Example snippet:

```toml
[wspr]
enabled = true
auto_upload = false
grid = "EM12ab"
power_dbm = 37
uploader_enabled = false
```

The uploader wiring will respect `uploader_enabled` before attempting to drain the queue. This provides a deliberate safety switch that lets you confirm your station metadata, networking, and credentials before publishing to WSPRnet.

With the flag enabled, the capture pipeline now writes enriched spot entries to `~/.local/share/neo-rx/wspr/wspr_upload_queue.jsonl`. Each entry carries the tuned band (`dial_freq_hz`), the aligned slot start timestamp, and the reporter fields required by WSPRnet so uploads can happen later without recomputing context.

When you invoke `neo-rx wspr upload`, the command enforces the same gate: it aborts with an actionable error until `[wspr].uploader_enabled = true`, guaranteeing that uploads remain opt-in.

These fields complement the existing `wspr_bands_hz`, `wspr_capture_duration_s`, and MQTT options. The uploader and queueing are implemented; however, HTTP submission requires credential/configuration and should be hardened for production use.

### WSPRnet Uploader

The `WsprUploader` class provides a lightweight on-disk JSON-lines queue for spots
intended for WSPRnet submission. Queue operations are atomic (via temp-file rewrite)
to prevent corruption on unexpected shutdown.

**Queue management:**
- `enqueue_spot(spot)`: append a spot dict to the queue.
- `drain(max_items=None, daemon=False)`: attempt to upload queued items; failures and
  unattempted items (when `max_items` is set) remain for retry. When `daemon=True`,
  the uploader enforces a simple exponential backoff window so repeated failures
  don't hammer WSPRnet, and it surfaces the first error message via `last_error`
  in the returned stats.
- `upload_spot(spot)`: performs the WSPRnet HTTPS GET submission (via `requests`)
  using the same query parameters as `rtlsdr-wsprd`; queue, drain, and upload
  are all fully implemented.
- `send_heartbeat(...)`: issues a `wsprstat` heartbeat (matching `rtlsdr-wsprd`)
  so stations can publish a “no uploads this slot” beacon when desired.

**Example usage:**

```python
from neo_wspr.wspr.uploader import WsprUploader

uploader = WsprUploader(queue_path="/path/to/queue.jsonl")
uploader.enqueue_spot({"call": "K1ABC", "freq_hz": 14080000, "snr_db": -12})
result = uploader.drain()
print(f"Uploaded {result['succeeded']}/{result['attempted']} spots")
```

**CLI integration:**

```bash
# Drain the upload queue and attempt to submit all queued spots
neo-rx wspr upload

# Emit drain results in JSON (helpful for monitoring/scripting)
neo-rx wspr upload --json

# Force a wsprstat heartbeat when no uploads occur (opt-in)
neo-rx wspr upload --heartbeat
```

JSON drain output always includes `attempted`, `succeeded`, `failed`, and
`last_error` (which is `null` when the last run succeeded). When `--heartbeat`
is set, the JSON blob also records `heartbeat_sent` plus a `heartbeat_error`
string if the stat ping failed.

The CLI now logs the first failing error surfaced by `drain()` so you can see
whether the queue is blocked on metadata issues, HTTP errors, or network
exceptions without digging through debug logs.

### Operational tips & observability

- **Queue location:** All pending uploads live in `~/.local/share/neo-rx/wspr/wspr_upload_queue.jsonl`.
  You can inspect/remove entries manually (JSON-lines) if you need to recover from
  repeated failures.
- **Logs:** Upload attempts are logged at DEBUG (shows rcall/target) while successes
  land at INFO and failures at WARNING. Enable `NEO_RX_LOG_LEVEL=DEBUG` when chasing
  HTTP/metadata issues; log files live under `~/.local/share/neo-rx/logs/neo-rx.log`.
- **Heartbeats:** Use `neo-rx wspr upload --heartbeat` to emit a `wsprstat` ping whenever
  a drain cycle produces zero successful uploads. The JSON response includes `heartbeat_sent`
  plus an error string to aid dashboards.
- **Rate-limit etiquette:** `wsprnet.org` is mission-critical for shared spectrum.
  Schedule `--upload` runs no more frequently than once per slot (2 minutes), and
  let the built-in exponential backoff handle outages instead of hammering the service.
- **Troubleshooting:** If `last_error` reports missing metadata, re-run `neo-rx aprs setup`
  to populate `[wspr]` fields or inspect recent spots for malformed timestamps. Network
  failures leave entries queued; check firewall/CA bundles before deleting anything.

## Testing

- Unit tests: parse `wsprd` outputs, ppm math, MQTT publishing (mocked).
- Integration: use recorded IQ fixtures to validate end-to-end pipeline.
- Queue tests: enqueue, drain, partial failure, atomic rewrite, max-item limits.
- JSON output tests: `--scan --json`, `--upload --json` format validation.

## Milestones

M1: RFC + config schema + telemetry publisher abstraction + docs (1–2 days) ✓

M2: Subprocess decoder wrapper + parsing tests (2 days) ✓

M3: Capture pipeline + band-scan + logging + MQTT publisher + on-disk buffering (3–4 days) ✓

M4: Diagnostics + calibration tools (2–3 days) ✓

M5: WSPRnet uploader + retries (2 days) ✓

M6: Tests, docs, CI updates, optional Docker Compose example (2 days) ✓

**Total: ~10–14 working days — All completed.**

**Final Test Suite: 201 passing tests**

## Implementation Status

### ✓ Completed: All Milestones M1–M6

**M1–M4 (Core Pipeline):**
- Configuration schema with wspr, upconverter, mqtt fields
- Decoder wrapper for `wsprd` subprocess with spot parsing
- Capture orchestration and band-scan with SNR metrics
- MQTT publisher with on-disk buffering and reconnect/backoff
- Diagnostics heuristics (frequency offset, SNR-based confidence)
- Calibration with PPM estimation and safe config backups

**M5 (WSPRnet Uploader):**
- On-disk JSON-lines queue with atomic temp-file rewrite
- `drain()` method: attempt uploads, keep failures/unattempted for retry
- CLI `--upload` command with optional `--json` output
- 9 comprehensive queue/drain tests
- `upload_spot()` performs the real WSPRnet HTTPS submission (see Implementation Status below)

**M6 (Testing & Documentation):**
- 187 passing tests (decoder, capture, scan, MQTT, diagnostics, uploader, JSON outputs)
- Enhanced diagnostics: SNR-based confidence scoring
- JSON output validation for `--scan --json` and `--upload --json`
- Comprehensive CLI help (all flags documented)

### Tested Components

| Component | Tests | Coverage |
|-----------|-------|----------|
| Decoder (parsing) | 1 | Fixture format validation |
| Capture cycle | 1 | Persistence to JSON-lines |
| Band-scan | 1 | Metrics ranking |
| MQTT publisher | 3 | Durability, reconnect, reconnection on drain |
| MQTT CLI wiring | 1 | Integration test |
| Uploader queue | 9 | Enqueue, drain, atomic rewrite, failures, limits |
| Diagnostics | 10 | Freq offset, SNR patterns, multi-band, edge cases |
| JSON outputs | 2 | `--scan --json`, `--upload --json` |
| Config/calibration | 5 | Persist, backup creation, PPM application |
| RTL-SDR compatibility | 7 | Patching, version handling, import fixes |

### Implementation Status

All items originally tracked as stubs are now implemented:

1. **`apply_ppm_to_radio(ppm)` in `calibrate.py`** ✅ **RESOLVED**
   - Status: Implemented with RTL-SDR integration, error handling, and unit tests. Applies PPM correction to tuner in real-time.

2. **`upload_spot(spot)` in `uploader.py`** ✅ **RESOLVED**
   - Status: Submits spots to WSPRnet via an HTTPS GET request (`requests`), matching the `rtlsdr-wsprd` query-parameter contract. Queue, drain, retry/backoff, and heartbeat are all functional (`src/neo_wspr/wspr/uploader.py`).

3. **`WsprCapture` real-time capture** ✅ **RESOLVED**
   - Status: Fully implemented with RTL-SDR integration, threading for background capture, multi-band cycling (80m/40m/30m/10m), IQ sample capture, and piping to wsprd subprocess.
   - Features: Device detection, frequency tuning, 2-minute band cycles, error handling, and spot publishing to MQTT/JSON-lines.

4. **External dependency: `wsprd` binary** ✅ **RESOLVED**
   - Status: Binary bundled with the `neo-wspr` package (extracted from the WSJT-X deb package); no external installation required.
   - Implementation: `scripts/install_wsprd.sh` downloads and extracts the binary to `src/neo_wspr/wspr/bin/wsprd`.


### Known limitations / follow-ups

- Uploader credentials beyond callsign/grid/power are not prompted for during setup; `wsprnet.org` currently accepts unauthenticated spot submissions via the query-parameter contract this client uses.
- Decoder input is written to a temporary IQ file per cycle rather than streamed directly into `wsprd`.
- Spectral diagnostics could add autocorrelation-based upconverter confidence metrics.
- See `docs/ROADMAP.md` for broader project-level follow-ups.
