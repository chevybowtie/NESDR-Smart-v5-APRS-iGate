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

## Scope

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

## Decoder Approach

- Start with a subprocess wrapper for `wsprd` (fast to prototype).
- Parse stdout/stderr for spots and drift; emit structured events.

## Reporting & Message Bus

- Local JSON-lines log of spots.
- MQTT publisher (topic `neo_igate/wspr/spots`) for dashboards.
- **On-disk buffering**: Messages are persisted to disk when the broker is
  unavailable and automatically sent when connection is restored.
- Buffer management with configurable size limits and automatic rotation.
- Optional auto-upload to WSPRnet with queue/retry and manual credential input.

## Testing

- Unit tests: parse `wsprd` outputs, ppm math, MQTT publishing (mocked).
- Integration: use recorded IQ fixtures to validate end-to-end pipeline.

## Milestones

M1: RFC + config schema + telemetry publisher abstraction + docs (1–2 days) ✓

M2: Subprocess decoder wrapper + parsing tests (2 days) ✓

M3: Capture pipeline + band-scan + logging + MQTT publisher + on-disk buffering (3–4 days) ✓

M4: Diagnostics + calibration tools (2–3 days)

M5: WSPRnet uploader + retries (2 days)

M6: Tests, docs, CI updates, optional Docker Compose example (2 days)

Total: ~10–14 working days.

## Next actions

1. Implement telemetry publisher abstraction and MQTT publisher.
2. Extend configuration schema to include `wspr`, `upconverter`, and `mqtt`.
3. Scaffold `src/neo_igate/wspr/` and tests.
