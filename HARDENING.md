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

5. **`adsb_aircraft.jsonl` grows forever.**
   [`src/neo_adsb/adsb/capture.py`](src/neo_adsb/adsb/capture.py) appends a
   JSON line per aircraft on each poll, with no rotation, size cap, or
   pruning. Even a modest ADS-B feed can produce hundreds of MB or more per
   month, which is a real long-term storage risk on small SBCs and Pi-class
   systems.

6. **`wspr_spots.jsonl` has the same unbounded-append pattern.**
   [`src/neo_wspr/wspr/capture.py`](src/neo_wspr/wspr/capture.py) writes one
   line per decoded spot to `wspr_spots.jsonl`, also with no bounds or
   retention policy. The volume is lower than ADS-B, but the same months-long
   growth issue applies.

7. **Log files use plain, non-rotating `FileHandler`s.**
   [`src/neo_core/cli.py`](src/neo_core/cli.py) configures file logging with
   `logging.FileHandler`, not a rotating handler. This is a deployment
   concern rather than a crash bug, but it makes unattended operation more
   fragile over time because the logs themselves are not bounded.

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

10. **No disk-space or queue-depth health check is surfaced in diagnostics.**
    The current diagnostics focus on SDR/network reachability, but they do
    not warn when the data or log filesystem is running low. Once the JSONL
    logs above are present for months at a time, free space becomes a more
    important health signal than raw connectivity.

## Minor

11. **`stats["unique_aircraft"]` grows without bound.**
    In [`src/neo_adsb/commands/listen.py`](src/neo_adsb/commands/listen.py),
    the per-process `set()` of seen aircraft hex IDs is never reset or capped.
    The impact is limited compared with the JSONL growth, but it is the same
    general pattern of "state accumulates forever".

## Recommended priority order

1. Make the APRS/WSPR capture loops detect dead subprocesses or failed
   devices and either restart the subsystem or exit non-zero so systemd can
   remediate the service (#1-4).
2. Add rotation or size limits to `adsb_aircraft.jsonl` and
   `wspr_spots.jsonl` (#5-6).
3. Publish complete systemd units for all three modes, including backoff and
   restart timing guidance (#8).
4. Fold or remove the legacy `neo_rx` package once compatibility imports are
   no longer needed (#9).

## Bottom line

The strongest current findings are not that neo-rx crashes; they are that it
can become silently degraded in APRS/WSPR, and that the JSONL/log artifacts
can grow without bound over long runs. Those are the issues most likely to
matter in a real months-long unattended deployment.
