# Hardening for long-running (months-scale) deployments

This document summarizes a reliability audit of the three listener modes
(APRS, WSPR, ADS-B) plus the shared telemetry/config code, focused on what
breaks — quietly — when neo-rx is left running unattended for weeks or
months under systemd. The common theme: individual operations are wrapped
in reasonable `try/except` blocks, but several failure modes leave the
process **silently degraded instead of restarting or exiting with an
error**, which defeats `Restart=on-failure` for exactly the scenario this
tool is meant to run in.

None of these are crash risks — the code is defensive about not raising.
The actual risk is the opposite: failures are absorbed so quietly that the
process keeps running in a non-functional state, or keeps running while
slowly filling the disk, and neither condition is visible to systemd or to
an operator without manually tailing logs.

## Critical — silent failures that won't self-heal

1. **rtl_fm death hangs the APRS listener forever, with no restart.**
   [`src/neo_aprs/commands/listen.py:154-171`](src/neo_aprs/commands/listen.py#L154-L171)
   — `_pump_audio()` reads from `rtl_fm` in a background thread. If it dies
   (USB drop, thermal shutdown — a documented long-run symptom, see
   [`docs/troubleshooting.md:1-5`](docs/troubleshooting.md#L1)), the thread
   exits and the error is only logged
   ([`listen.py:372`](src/neo_aprs/commands/listen.py#L372)). The main loop
   keeps polling KISS frames forever with no audio flowing and no attempt
   to relaunch `rtl_fm`. The process looks "alive" to systemd indefinitely.

2. **Direwolf dying isn't actively detected.** Same function only checks
   `direwolf_proc.stdin is None`, never `direwolf_proc.poll()`. A dead
   Direwolf is only noticed once a `BrokenPipeError` surfaces on write, and
   even then there's no respawn logic.

3. **WSPR capture failures exit with code 0, so `Restart=on-failure` never
   fires.** [`src/neo_wspr/wspr/capture.py:122-374`](src/neo_wspr/wspr/capture.py#L122-L374)
   — any exception escaping the outer `try` (no RTL-SDR found, device init
   failure, driver crash) sets `self._running = False` and returns. Back in
   [`commands/listen.py:140`](src/neo_wspr/commands/listen.py#L140), the
   outer `while capture.is_running()` loop exits normally and `run_listen`
   returns 0. The sample systemd unit
   ([`docs/INSTALL.md:66-78`](docs/INSTALL.md#L66-L78)) only restarts on a
   non-zero exit or signal — a clean exit-0 after a hardware fault means the
   service just stops and stays stopped.

4. **Mid-run SDR glitches in WSPR spin silently.** The `RtlSdr()` object is
   acquired once for the whole run; a transient USB hiccup on one band is
   caught by the per-band `except Exception: continue`
   ([`capture.py:362-364`](src/neo_wspr/wspr/capture.py#L362-L364)) without
   ever re-initializing the device, so a stuck/wedged SDR can loop through
   all 8 bands failing every 2 minutes indefinitely.

## High — unbounded on-disk growth

5. **`adsb_aircraft.jsonl` grows forever.**
   [`src/neo_adsb/adsb/capture.py:213`](src/neo_adsb/adsb/capture.py#L213)
   / [`333-354`](src/neo_adsb/adsb/capture.py#L333-L354) — appends a JSON
   line per tracked aircraft on every poll (default 1 Hz), no rotation,
   size cap, or pruning. Even with a handful of aircraft visible, this is
   hundreds of MB to low GB per month — the single biggest threat to
   multi-month operation on typical Pi/SBC storage.

6. **`wspr_spots.jsonl` has the same unbounded-append pattern.**
   ([`capture.py:76`](src/neo_wspr/wspr/capture.py#L76),
   [`412-417`](src/neo_wspr/wspr/capture.py#L412-L417)) Lower volume (one
   line per decoded spot per 2-minute cycle) so less urgent, but still
   uncapped for a single long-lived process.

7. **Log files use a plain, non-rotating `FileHandler`.**
   ([`src/neo_core/cli.py:249`](src/neo_core/cli.py#L249)) At least
   documented — [`docs/diagnostics.md:156-172`](docs/diagnostics.md#L156)
   tells users to configure host-level `logrotate` — but that guidance only
   covers `*.log`, not the two data files above, and it's opt-in/manual.

## Medium

8. **Systemd guidance is incomplete for a months-long deployment.** The
   only sample unit ([`docs/INSTALL.md:66-78`](docs/INSTALL.md#L66-L78))
   covers APRS only (no WSPR/ADS-B units), sets `Restart=on-failure` with
   no `RestartSec`/`StartLimitBurst`, so a persistent fault (unplugged
   dongle) will rapid-restart-loop until systemd's default burst limit
   disables the unit — with no alerting to notice.

9. **Legacy duplicate package (`src/neo_rx/`) is still live in the import
   graph.** Nearly every active module falls back to
   `from neo_rx import __version__`
   ([`listen.py:31`](src/neo_aprs/commands/listen.py#L31),
   [`aprsis_client.py:15`](src/neo_aprs/aprs/aprsis_client.py#L15),
   [`uploader.py:16`](src/neo_wspr/wspr/uploader.py#L16), etc.), and root
   [`pyproject.toml`](pyproject.toml) still packages `neo_rx` while the
   actual entry point is `neo_core.cli:main`. It's been frozen since
   2026-07-24 while `neo_core` etc. are actively developed — a fix landed
   in the new packages has no reason to also land in the old tree, and vice
   versa. Low risk today, but it's exactly the kind of drift that produces
   a confusing "I already fixed that" bug months from now.

10. **No disk-space or queue-depth health check.** `diagnostics` checks
    SDR/network reachability well, but nothing warns about free space on
    the data/log filesystem — the metric that matters most once items
    #5-7 are in play over a multi-month run.

## Minor

11. **`stats["unique_aircraft"]` set** in
    [`src/neo_adsb/commands/listen.py:174-176`](src/neo_adsb/commands/listen.py#L174-L176)
    grows for the life of the process with no cap. Real-world impact is
    small (a few thousand hex strings over months) but it's part of the
    same "nothing is ever pruned" pattern.

## Recommended priority order

1. Make the APRS/WSPR capture loops detect their own subprocess/device
   death and either restart the subprocess or exit non-zero, so systemd can
   restart the service (#1-4).
2. Add rotation or a size cap to `adsb_aircraft.jsonl` and
   `wspr_spots.jsonl` (#5-6).
3. Ship complete systemd units for all three modes with
   `RestartSec=`/backoff guidance (#8).
4. Fold or delete the frozen `neo_rx` package once nothing still needs it
   (#9).
