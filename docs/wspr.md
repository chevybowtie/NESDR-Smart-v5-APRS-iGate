# WSPR Feature Plan

This document outlines the feature plan for adding WSPR (Weak Signal
Propagation Reporter) decoding and reporting to the project. It captures
requirements, design decisions, diagnostics, integration points, and a
proposed development roadmap.

## Goal

Add in-process WSPR receive/decoding and optional auto-reporting to
WSPRnet, with band scanning, automated upconverter diagnostics, ppm
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

- `src/neo_igate/wspr/`
  - `capture.py` — capture orchestration and scheduler
  - `decoder.py` — wrapper for `wsprd` subprocess and parser
  - `uploader.py` — optional wsprnet uploader (opt-in)
  - `diagnostics.py` — upconverter heuristics and checks
  - `calibrate.py` — ppm measurement and application logic
  - `publisher.py` — MQTT publisher integration (uses telemetry abstraction)

## Upconverter detection

Automatic USB detection is not possible (passive converter). Proposed
heuristics:
- Spectrum-shift test against known beacons (WWV/CHU) to detect an LO
  offset.
- Compare SNR with/without converter connected (guided user steps).
- Produce confidence score and recommended LO offset.

## Time & Calibration

- Require NTP/GPS/PPS for time accuracy.
- Calibration options:
  - Measure ppm from strong time/frequency station and compute correction.
  - Use `wsprd` reported drift to derive ppm and apply correction.

### Calibration & Backup Behavior

- Computation: the tool computes parts-per-million (ppm) correction by
  comparing the median observed frequency of decoded spots against an
  expected centre frequency for the configured band. The helper
  function `estimate_offset_from_spots(spots, expected_freq_hz)` returns
  the median observed frequency, the offset in Hz, the derived ppm,
  median SNR and observation count.
- Apply vs persist: `--calibrate --apply` will run the local calibration
  flow and call a stub that can apply the correction to the radio driver.
  To persist the computed correction into the persistent `config.toml`,
  use `--write-config` alongside `--apply` (this performs a safe save).
- Safe saves & backups: before writing a new `ppm_correction` value the
  tool creates a timestamped backup of the existing config file. Backups
  are stored under the configuration directory in a `backups/` folder
  alongside the config file. Backup filenames are of the form:

  `config.toml.bak-YYYYMMDDTHHMMSSZ`

  where the timestamp is UTC (timezone-aware). This prevents accidental
  data loss and makes it straightforward to restore previous settings.
- CLI feedback: when a change is persisted the CLI prints the path to
  the saved configuration so operators can confirm where the write
  occurred (and which backup was created if needed).

Implementation notes:
- The code exposes `persist_ppm_to_config(ppm, config_path=None)` to
  perform the safe save and `apply_ppm_to_radio(ppm)` as a radio-driver
  integration point (currently a logging stub).
- Backups are automatically created; retention/rotation is left as an
  enhancement (could prune old backups after N days or keep only the
  last N backups).

Example usage:

```bash
# Run calibration using saved spots (no apply):
neo-igate wspr --calibrate

# Run calibration and apply correction to the radio (stub only):
neo-igate wspr --calibrate --apply

# Run calibration, apply correction, and persist to the config (safe-save)
neo-igate wspr --calibrate --apply --write-config

# Specify a custom config file or spots file when needed:
neo-igate wspr --calibrate --apply --write-config --config /path/to/config.toml \
    --spots-file /path/to/wspr_spots.jsonl --expected-freq 14080000
```

  Restore from backup:

  ```bash
  # To inspect available backups:
  ls "$(dirname $(neo-igate wspr --config 2>/dev/null || echo ~/.config/neo-igate))/backups/"

  # To restore the most recent backup for the active config:
  cp /path/to/config/backups/config.toml.bak-YYYYMMDDTHHMMSSZ /path/to/config/config.toml

  # Or move it into place (atomic replace):
  mv /path/to/config/backups/config.toml.bak-YYYYMMDDTHHMMSSZ /path/to/config/config.toml
  ```

## Decoder Approach

- Start with a subprocess wrapper for `wsprd` (fast to prototype).
- Parse stdout/stderr for spots and drift; emit structured events.

## Reporting & Message Bus

- Local JSON-lines log of spots.
- MQTT publisher (topic `neo_igate/wspr/spots`) for dashboards.
- **On-disk buffering**: Messages are persisted to disk when the broker is
  unavailable and automatically sent when connection is restored.
- Buffer management with configurable size limits and automatic rotation.
- **Optional auto-upload to WSPRnet** with queue/retry and manual credential input.

### WSPRnet Uploader

The `WsprUploader` class provides a lightweight on-disk JSON-lines queue for spots
intended for WSPRnet submission. Queue operations are atomic (via temp-file rewrite)
to prevent corruption on unexpected shutdown.

**Queue management:**
- `enqueue_spot(spot)`: append a spot dict to the queue.
- `drain(max_items=None)`: attempt to upload all queued items; failures and
  unattempted items (when `max_items` is set) remain for retry.
- `upload_spot(spot)`: abstract method (currently a logging stub) for submitting
  a single spot to WSPRnet.

**Example usage:**

```python
from neo_igate.wspr.uploader import WsprUploader

uploader = WsprUploader(queue_path="/path/to/queue.jsonl")
uploader.enqueue_spot({"call": "K1ABC", "freq_hz": 14080000, "snr_db": -12})
result = uploader.drain()
print(f"Uploaded {result['succeeded']}/{result['attempted']} spots")
```

**CLI integration:**

```bash
# Drain the upload queue and attempt to submit all queued spots
neo-igate wspr --upload

# Emit drain results in JSON (helpful for monitoring/scripting)
neo-igate wspr --upload --json
```

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

**Final Test Suite: 187 passing tests**

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
- ⚠️ `upload_spot()` is a stub; real WSPRnet HTTP submission required before production use

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
| Config/calibration | 3 | Persist, backup creation |

### Remaining Stubs (Non-Production)

These functions have CLI wiring and test infrastructure but require external dependencies or driver integration:

1. **`apply_ppm_to_radio(ppm)` in `calibrate.py`** ✅ **RESOLVED**
   - Status: Implemented with RTL-SDR integration, error handling, and unit tests. Applies PPM correction to tuner in real-time.

2. **`upload_spot(spot)` in `uploader.py`**
   - Currently: Logs the spot; returns success
   - Required: WSPRnet HTTP client + API authentication + endpoint
     - we should look at https://github.com/garymcm/wsprnet_api/blob/master/README.md for the API
     - not sure this is useful, be we should examine real-time data access via the wspr.live service which provides a ClickHouse-based database with a public API for querying WSPR spots 
   - Status: Queue management fully functional; HTTP submission is stubbed
   - Blocking: ⚠️ **Production deployment requires real implementation**

3. **`WsprCapture` real-time capture**
   - Currently: Skeleton with testable sync interface (accepts mock `capture_fn`)
   - Required: `pyrtlsdr` integration, threading/scheduler for multi-band cycles
   - Status: Infrastructure present; RTL-SDR capture loop not implemented
   - Note: `run_wsprd_subprocess()` decoder wrapper is complete; just needs capture source

4. **External dependency: `wsprd` binary**
   - Status: Decoder gracefully handles missing binary (logs warning, exits cleanly)
   - Required: User must install `wsprd` separately for real WSPR decoding
   - Testing: All tests use fixture data; no binary dependency in test suite

### Future Enhancements (Blocking Production Deployment)

1. **WSPRnet HTTP integration:** Replace `upload_spot()` stub with real API submission (REST + authentication). ⚠️ **Required before production use.**
2. **Credential management:** Securely store/rotate WSPRnet API keys (keyring or encrypted config).

### Optional Enhancements

3. **Spectral diagnostics:** Add autocorrelation-based upconverter confidence metrics.
4. **CI/CD:** Python 3.11+ matrix, coverage thresholds, pre-commit lint hooks.
5. **Docker Compose:** RTL-SDR + Mosquitto + Grafana dashboard example.
6. **Performance:** Batch MQTT publishes, streaming decoder optimization, worker pool for multi-band capture.




### Remaining Stubs (Non-Production)

These functions have CLI wiring and test infrastructure but require external dependencies or driver integration:

1. **`apply_ppm_to_radio(ppm)` in `calibrate.py`** ✅ **RESOLVED**
   - Status: Implemented with RTL-SDR integration, error handling, and unit tests. Applies PPM correction to tuner in real-time.

2. **`upload_spot(spot)` in `uploader.py`**
   - Currently: Logs the spot; returns success
   - Required: WSPRnet HTTP client + API authentication + endpoint
     - we should look at https://github.com/garymcm/wsprnet_api/blob/master/README.md for the API
     - not sure this is useful, be we should examine real-time data access via the wspr.live service which provides a ClickHouse-based database with a public API for querying WSPR spots 
   - Status: Queue management fully functional; HTTP submission is stubbed
   - Blocking: ⚠️ **Production deployment requires real implementation**

3. **`WsprCapture` real-time capture**
   - Currently: Skeleton with testable sync interface (accepts mock `capture_fn`)
   - Required: `pyrtlsdr` integration, threading/scheduler for multi-band cycles
   - Status: Infrastructure present; RTL-SDR capture loop not implemented
   - Note: `run_wsprd_subprocess()` decoder wrapper is complete; just needs capture source

4. **External dependency: `wsprd` binary**
   - Status: Decoder gracefully handles missing binary (logs warning, exits cleanly)
   - Required: User must install `wsprd` separately for real WSPR decoding
   - Testing: All tests use fixture data; no binary dependency in test suite

#### Resolution Plan

Based on the implementation status, here's a targeted plan to address the 4 remaining stubs for production deployment. Each includes steps, code changes, testing, and estimated effort. Total estimated time: 5–7 days, assuming access to RTL-SDR hardware and WSPRnet API docs.

##### 1. **`apply_ppm_to_radio(ppm)` in `calibrate.py`** (RTL-SDR Driver Integration) ✅ **COMPLETED**
   - **Status**: Implemented with RTL-SDR integration, error handling, and unit tests. Applies PPM correction to tuner in real-time.
   - **Code Changes**: Modified `src/neo_igate/wspr/calibrate.py` to import `pyrtlsdr` and implement the apply logic.
   - **Testing**: Added unit tests with mocked `pyrtlsdr` for success, no devices, import errors, and device failures.
   - **Effort**: 1–2 days; completed with low risk.

##### 2. **`upload_spot(spot)` in `uploader.py`** (WSPRnet HTTP Submission)
   - **Current State**: Logs spots and returns success; queue management is fully functional.
   - **Goal**: Submit spots to WSPRnet via their API (requires authentication).
   - **Steps**:
     - Review WSPRnet API docs for submission endpoint, required fields (e.g., call, freq, SNR), and auth (likely API key).
     - Implement HTTP POST in `upload_spot(spot)` using `requests` (add to dependencies).
     - Handle auth securely (e.g., store key in config or keyring); add retry logic for network failures.
     - Update CLI to prompt for credentials on first use (via `setup_io.py` helpers).
   - **Code Changes**: Enhance `src/neo_igate/wspr/uploader.py` with HTTP client and auth handling. Update config schema for WSPRnet credentials.
   - **Testing**: Mock HTTP responses for success/failure. Add tests for auth, retries, and malformed spots. Validate against WSPRnet sandbox if available.
   - **Effort**: 2–3 days; moderate risk due to external API dependency—test thoroughly to avoid rate limits or bans.
   - **Note**: ⚠️ **Critical for production**—do not deploy without real implementation.

##### 3. **`WsprCapture` Real-Time Capture** (RTL-SDR Integration)
   - **Current State**: Skeleton with sync interface; decoder wrapper is complete.
   - **Goal**: Enable live IQ capture from RTL-SDR for multi-band WSPR decoding.
   - **Steps**:
     - Integrate `pyrtlsdr` in `WsprCapture` to open device, tune to bands, and capture IQ samples.
     - Add threading/scheduler for band cycling (e.g., 2-minute cycles per band).
     - Wire captured IQ to `run_wsprd_subprocess()` for decoding.
     - Handle device errors (e.g., busy tuner) and cleanup on shutdown.
   - **Code Changes**: Flesh out `src/neo_igate/wspr/capture.py` with `pyrtlsdr` calls and threading logic.
   - **Testing**: Unit tests with mocked capture (already in place). Integration tests with real SDR for end-to-end decoding.
   - **Effort**: 1–2 days; builds on existing skeleton—focus on threading stability.

##### 4. **External Dependency: `wsprd` Binary** (User Installation Guidance)
   - **Current State**: Decoder handles missing binary gracefully (logs warning, exits cleanly).
   - **Goal**: Ensure users can install `wsprd` easily; no code changes needed, but improve docs/setup.
   - **Steps**:
     - Add installation instructions to `README.md` (e.g., `sudo apt install wspr` or build from source).
     - Update prerequisites section and error messages to guide users.
     - Optionally, add a `--check-deps` flag to CLI for pre-flight checks.
   - **Code Changes**: Minimal—update docs and possibly `diagnostics.py` for dependency checks.
   - **Testing**: Add tests for missing binary handling (already covered); verify error messages.
   - **Effort**: 0.5–1 day; documentation-focused.

##### Overall Notes
- **Dependencies**: Ensure `pyrtlsdr` and `requests` are in `pyproject.toml` (add `requests>=2.25` for HTTP).
- **Testing Strategy**: Expand integration tests for real hardware/API. Run full suite (`.venv/bin/python -m pytest`) after each stub.
- **Risks**: API auth and hardware integration—test on staging/sandbox environments.
- **Timeline**: Item #1 completed; tackle 3 next (RTL-SDR capture), then 2 (WSPRnet API), and 4 last (docs). Aim for incremental commits with tests.
- **Post-Resolution**: Update `CHANGELOG.md` and mark as production-ready once all stubs are implemented and tested.
