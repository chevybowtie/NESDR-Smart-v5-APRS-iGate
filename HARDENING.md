# Hardening for long-running (months-scale) deployments

This document summarizes a reliability audit of the three listener modes
(APRS, WSPR, ADS-B) plus the shared telemetry/config code, focused on what
breaks — quietly — when neo-rx is left running unattended for weeks or
months under systemd.

The overall pattern is consistent: the code is generally defensive and tries
not to raise, but several failure modes are absorbed into logs and state
changes rather than causing the process to self-heal, exit non-zero, or
surface an obvious operator-visible error. That is exactly the kind of
behavior that defeats `Restart=on-failure` during long-lived deployments.

None of the items below are crash bugs in the usual sense. The main risk is
not a process crash; it is a process that remains "alive" while silently
stopping useful work, or continues appending to disk until storage is
exhausted.

## Critical — silent failures that won't self-heal

1. **APRS audio capture can die without being restarted.**
   In [`src/neo_aprs/commands/listen.py`](src/neo_aprs/commands/listen.py),
   `_pump_audio()` reads from the `RtlFmAudioCapture` stream in a background
   thread. When `capture.read()` hits EOF or an unexpected error, the thread
   stops and the error is only queued for later reporting. The main loop
   continues polling KISS frames, but there is no restart of `rtl_fm` and no
   non-zero exit that would tell systemd to restart the service.

2. **Direwolf death is not actively detected or repaired.**
   The APRS listener only checks `direwolf_proc.stdin is None` before writing
   audio, and it never actively polls `direwolf_proc.poll()` to detect a dead
   child. A dead Direwolf is therefore only noticed indirectly when a
   `BrokenPipeError` occurs during writes, and even then there is no
   respawn path.

3. **WSPR capture can exit cleanly after a hardware/init failure, so
   `Restart=on-failure` does not fire.**
   In [`src/neo_wspr/wspr/capture.py`](src/neo_wspr/wspr/capture.py), broad
   exceptions in `_capture_loop()` set `self._running = False` and return.
   The outer loop in [`src/neo_wspr/commands/listen.py`](src/neo_wspr/commands/listen.py)
   then exits normally, and `run_listen()` returns 0. That means a device
   not found, driver/init failure, or similar hardware problem can look like
   a normal shutdown to systemd.

4. **Mid-run SDR glitches in WSPR can spin forever without reinitializing
   the device.**
   The SDR object is created once at the start of the WSPR capture loop and
   then reused across all bands. When a per-band exception occurs, the
   current code logs the error and `continue`s to the next band instead of
   reopening or replacing the RTL-SDR handle. In practice, that means a
   wedged or partially failed USB device can cause repeated band-by-band
   failures for the entire run.

## High — unbounded on-disk growth

5. **RESOLVED — `adsb_aircraft.jsonl` grows forever.**
   [`src/neo_adsb/adsb/capture.py`](src/neo_adsb/adsb/capture.py) now writes
   through a `RotatingJsonlWriter`
   ([`src/neo_core/rotation.py`](src/neo_core/rotation.py)) that rotates the
   file weekly and retains 12 weeks of backups by default. Override via the
   `NEO_RX_ADSB_LOG_RETENTION_WEEKS` environment variable.

6. **RESOLVED — `wspr_spots.jsonl` had the same unbounded-append pattern.**
   [`src/neo_wspr/wspr/capture.py`](src/neo_wspr/wspr/capture.py) now writes
   through the same `RotatingJsonlWriter` helper, rotating weekly with a
   12-week default retention. Override via the
   `NEO_RX_WSPR_LOG_RETENTION_WEEKS` environment variable.

7. **RESOLVED — Log files used plain, non-rotating `FileHandler`s.**
   [`src/neo_core/cli.py`](src/neo_core/cli.py) now configures file logging
   with a `TimedRotatingFileHandler` (via
   [`src/neo_core/rotation.py`](src/neo_core/rotation.py)) that rotates
   `neo-rx.log` weekly and retains 12 weeks of backups by default. Override
   via the `NEO_RX_LOG_RETENTION_WEEKS` environment variable.

## Medium

8. **Systemd guidance is incomplete for a long-lived deployment.**
   The sample unit in [`docs/INSTALL.md`](docs/INSTALL.md) covers APRS only,
   and the examples do not include the full set of durability controls that
   are helpful in practice for a months-scale deployment (`RestartSec`,
   `StartLimitBurst`, `StartLimitIntervalSec`, and per-mode service units).
   This is a deployment/documentation gap more than a code bug, but it is
   still important for real-world reliability.

9. **Legacy duplicate package (`src/neo_rx/`) remains a compatibility-risk
   drift point.**
   The active entry point is [`src/neo_core/cli.py`](src/neo_core/cli.py), but
   the legacy tree in [`src/neo_rx/`](src/neo_rx/) still exists and some
   modules continue to import/version-check it as a fallback. That is not the
   main runtime failure mode today, but it is a genuine maintenance risk:
   future fixes can land in one tree without the other, creating confusing
   "I already fixed that" bugs later.

10. **RESOLVED — No disk-space health check was surfaced in diagnostics.**
    All three diagnostics commands (APRS, WSPR, ADS-B) now report free disk
    space on the relevant data directory via a shared
    `check_disk_space()` helper in
    [`src/neo_core/diagnostics_helpers.py`](src/neo_core/diagnostics_helpers.py).
    Warning/error thresholds default to 10%/3% free and are overridable via
    `NEO_RX_DISK_WARN_PERCENT_FREE` / `NEO_RX_DISK_ERROR_PERCENT_FREE`. (The
    queue-depth half of this item — e.g. the WSPR upload queue backing up
    during an outage — is not yet covered; left as a follow-up.)

## Minor

11. **RESOLVED — `stats["unique_aircraft"]` grew without bound.**
    In [`src/neo_adsb/commands/listen.py`](src/neo_adsb/commands/listen.py),
    the per-process set of seen aircraft hex IDs is now a bounded LRU
    (default 10,000 entries, overridable via
    `NEO_RX_ADSB_UNIQUE_AIRCRAFT_CAP`) used only for membership checks; the
    displayed "unique aircraft seen" total is tracked separately as a plain
    counter, so it stays accurate even after old entries are evicted.

## Recommended priority order

1. Make the APRS/WSPR capture loops detect dead subprocesses or failed
   devices and either restart the subsystem or exit non-zero so systemd can
   remediate the service (#1-4).
2. ~~Add rotation or size limits to `adsb_aircraft.jsonl` and
   `wspr_spots.jsonl` (#5-6).~~ Done — see #5-7.
3. Publish complete systemd units for all three modes, including backoff and
   restart timing guidance (#8).
4. Fold or remove the legacy `neo_rx` package once compatibility imports are
   no longer needed (#9).

## Bottom line

The strongest current findings are not that neo-rx crashes; they are that it
can become silently degraded in APRS/WSPR, and that the JSONL/log artifacts
can grow without bound over long runs. Those are the issues most likely to
matter in a real months-long unattended deployment.
