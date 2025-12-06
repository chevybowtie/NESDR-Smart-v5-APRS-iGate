"""POCSAG scan command implementation.

Scans a frequency range for POCSAG pager activity.
"""

from __future__ import annotations

import json
import logging
from argparse import Namespace

from neo_core import config as config_module

LOG = logging.getLogger(__name__)


def run_scan(args: Namespace) -> int:
    """Run POCSAG frequency scan and report activity."""
    cfg_path = getattr(args, "config", None)
    cfg = None
    try:
        if cfg_path:
            cfg = config_module.load_config(cfg_path)
        else:
            cfg = config_module.load_config()
    except Exception:
        LOG.debug("No configuration available; using defaults")

    # Get scan parameters
    start_freq = getattr(args, "start_frequency", 152_000_000)
    end_freq = getattr(args, "end_frequency", 158_000_000)
    step_hz = getattr(args, "step_hz", 10_000)
    dwell_s = getattr(args, "dwell_seconds", 120)

    LOG.info("Running POCSAG frequency scan: %d - %d Hz (step: %d Hz, dwell: %d s)",
             start_freq, end_freq, step_hz, dwell_s)

    # Generate frequency list
    frequencies = list(range(start_freq, end_freq + 1, step_hz))

    def _capture_fn(freq_hz: int, dur: int):
        """Capture function for scanning: runs POCSAG capture and collects messages."""
        from neo_pocsag.pocsag.capture import PocsagCapture  # type: ignore[import]

        messages = []
        capture = None

        def _on_message(message):
            messages.append(message)

        try:
            capture = PocsagCapture(
                frequency_hz=freq_hz,
                gain=getattr(args, "gain", None),
                ppm=getattr(args, "ppm", 0),
                device_index=getattr(args, "device_index", 0),
            )
            capture.add_callback(_on_message)
            capture.start()

            import time
            time.sleep(dur)

        except Exception as e:
            LOG.debug("Capture failed on frequency %s: %s", freq_hz, e)
        finally:
            try:
                if capture is not None:
                    capture.stop()
                    import time
                    time.sleep(1)  # Allow SDR device to be released
            except Exception as e:
                LOG.debug("Stop failed on frequency %s: %s", freq_hz, e)

        return messages

    from neo_pocsag.pocsag.scan import scan_frequencies  # type: ignore[import]

    try:
        reports = scan_frequencies(frequencies, _capture_fn, dwell_s)
    except KeyboardInterrupt:
        LOG.info("Scan interrupted by user")
        # Return empty reports if interrupted
        reports = []

    # Emit JSON if requested, otherwise human-readable logs
    if getattr(args, "json", False):
        print(json.dumps(reports, indent=2, default=str))
        return 0

    # Print report
    active_freqs = [r for r in reports if r.get("message_count", 0) > 0]
    if active_freqs:
        LOG.info("Found POCSAG activity on %d frequencies:", len(active_freqs))
        for r in active_freqs:
            freq_mhz = r.get("frequency_hz", 0) / 1_000_000
            LOG.info(
                "%.3f MHz: %d messages, %d unique addresses",
                freq_mhz,
                r.get("message_count", 0),
                r.get("unique_addresses", 0),
            )
    else:
        LOG.info("No POCSAG activity detected in scanned range")

    return 0