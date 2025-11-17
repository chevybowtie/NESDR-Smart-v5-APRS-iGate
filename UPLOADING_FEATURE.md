# WSPRnet Uploading Feature Plan

This document captures the concrete plan for finishing the WSPRnet uploader in `neo-rx`, based on the proven implementation in [`rtlsdr-wsprd`](https://github.com/Guenael/rtlsdr-wsprd). Store all updates here so the plan survives restarts and context resets.

---

## 1. Goals

- Automatically submit decoded WSPR spots to [wsprnet.org](https://wsprnet.org).
- Reuse the existing on-disk queue so uploads survive restarts or network outages.
- Mirror rtlsdr-wsprd’s HTTP contract (parameters, formatting, timing) for compatibility.
- Keep credentials/configuration in our existing `StationConfig` + CLI, with secure storage options.

## 2. Current State (feature/WSPR branch)

- `WsprUploader` already provides a durable JSON-lines queue plus `drain()` and CLI wiring (`neo-rx wspr --upload`).
- `upload_spot()` is still a stub that just logs success.
- Spot records (written to `wspr_spots.jsonl`) already contain decoded data: frequency, dt, drift, snr, target call/grid, etc.
- Station identity (callsign, lat/long) lives in `config.toml`, but we do **not** yet persist a Maidenhead grid or reporter power dBm.

## 3. WSPRnet HTTP Contract

rtlsdr-wsprd hits two GET endpoints:

| Purpose | `function` | Required params |
| --- | --- | --- |
| Spot upload | `wspr` | `rcall`, `rgrid`, `rqrg`, `date`, `time`, `sig`, `dt`, `tqrg`, `tcall`, `tgrid`, `dbm`, `version`, `mode` (=`2`) |
| Empty/stat ping | `wsprstat` | `rcall`, `rgrid`, `rqrg`, `tpct`, `tqrg`, `dbm`, `version`, `mode` |

Implementation choices:

- Use HTTPS GET just like rtlsdr-wsprd for maximum compatibility. (POST is optional but not required.)
- Build query strings with six-decimal-place MHz frequencies and zero-padded UTC date/time representing the start of the 2‑minute slot (`tm_year-100`, etc.).
- Provide a project-specific version string (`neo-rx-<semver>`), max 10 characters.

## 4. Data Mapping (neo-rx → WSPRnet)

| WSPRnet field | Source in neo-rx | Notes |
| --- | --- | --- |
| `rcall` | `StationConfig.callsign` | Already required for APRS. |
| `rgrid` | **New**: add `wspr_grid` to config or derive from lat/long (Maidenhead 6). |
| `dbm` | **New**: cfg value (`wspr_power_dbm`), default 37 (5 W) or user-provided. |
| `rqrg` | Band dial frequency (Hz) / 1e6 | From capture band mapping. |
| `date` / `time` | Spot timestamp rounded to even minute | Already logged when spot captured. |
| `sig`, `dt`, `drift` | Parsed from `wsprd` output | Ensure float formatting matches WSJT-X (sig=%.0f, dt=%.1f). |
| `tqrg` | `spot["freq_hz"] / 1e6` | Already available. |
| `tcall` / `tgrid` / `pwr` | From decoder | Validate they exist before enqueue. |
| `version` | Hardcode `neo-rx-XYZ` | Keep ≤10 chars. |
| `mode` | Always `2` (per rtlsdr-wsprd). | |

## 5. Implementation Steps

1. **Config/schema updates** ✅ (2025-11-16)
   - `StationConfig` now persists `wspr.grid`, `wspr.power_dbm`, and `wspr.uploader_enabled` with sensible defaults (grid optional, power defaults to 37 dBm, uploader disabled by default).
   - `README.md` and `docs/wspr.md` document how to configure the new fields, including a sample `[wspr]` snippet for `config.toml`.
   - Regression coverage added in `tests/test_config.py` to ensure the new fields survive a save/load round-trip.
   - Maidenhead auto-derivation remains optional and is tracked in the open questions below.

2. **Spot enrichment** ✅ (2025-11-16)
   - `WsprCapture` now enriches every decoded spot (in-memory, on-disk, and queued) with `dial_freq_hz`, the aligned `slot_start_utc`, and reporter metadata sourced from `StationConfig`.
   - The capture CLI instantiates a persistent `wspr_upload_queue.jsonl` beneath the WSPR data directory whenever `wspr_uploader_enabled=true`; enriched spots are appended automatically.
   - If the reporter grid/power/slot metadata is missing, the uploader queue is skipped with a clear warning so partial data never enters the backlog.

3. **HTTP upload logic (`upload_spot`)**
   - Replace the stub with real network code using `requests` (add dep to `pyproject.toml`).
   - Build query params exactly as rtlsdr-wsprd does (see `postSpots()` in `rtlsdr_wsprd.c`).
   - Use a shared `requests.Session` with `timeout=5s` (connect) / `10s` (read) and TLS verification.
   - Treat non-200 status or empty body as failure (`return False`) so the queue keeps the spot.

4. **Queue & retry behavior**
   - Keep existing JSON-lines queue; after each drain attempt, keep failed/unattempted entries.
   - Add simple exponential backoff tracking when drain is invoked in daemon mode (so repeated failures don’t hammer WSPRnet).
   - Surface first error message back to CLI for easier diagnostics.

5. **CLI updates**
   - Allow `neo-rx wspr --upload` to optionally force a `wsprstat` heartbeat when no spots were uploaded (mirrors rtlsdr-wsprd’s empty-report behavior).
   - Support `--json` output containing success/failure counts plus a `last_error` string.

6. **Testing**
   - Unit tests in `tests/test_wspr_uploader.py`:
     - Happy-path upload: verify query string and `requests` calls via mocking.
     - Network failures / timeouts: ensure spot stays in queue.
     - Missing config: uploader refuses to run and logs actionable message.
     - `max_items` behavior still works with real uploader logic.
   - Optional integration test using `responses` or a tiny HTTP server fixture.

7. **Observability & docs**
   - Log each upload attempt at DEBUG and successes/failures at INFO.
   - Document operational steps in `docs/wspr.md` (credential setup, queue location, troubleshooting tips, rate-limit etiquette).

## 6. Open Questions / Follow-ups

1. Should we auto-derive `wspr_grid` from lat/long or require explicit entry? (Decision pending.)
2. Do we want batched uploads (multiple spots per HTTP call) later? Not required for parity.
3. Consider implementing optional proxy support via environment variables for headless deployments.

---

_Last updated: 2025-11-16_
