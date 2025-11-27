"""WSPR scan command implementation.

Runs a quick multi-band scan to detect WSPR activity.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from argparse import Namespace

from neo_core import config as config_module

LOG = logging.getLogger(__name__)


def run_scan(args: Namespace) -> int:
    """Run multi-band WSPR scan and report activity."""
    cfg_path = getattr(args, "config", None)
    cfg = None
    try:
        if cfg_path:
            cfg = config_module.load_config(cfg_path)
        else:
            cfg = config_module.load_config()
    except Exception:
        LOG.debug("No configuration available; using defaults")

    LOG.info("Running WSPR band-scan")

    # Determine bands to scan
    if cfg and getattr(cfg, "wspr_bands_hz", None):
        bands = cfg.wspr_bands_hz
    else:
        bands = [14_080_000, 7_080_000, 3_572_000, 50_294_800, 144_489_000, 432_500_000]

    duration = getattr(cfg, "wspr_capture_duration_s", 120) if cfg else 120

    def _capture_fn(band_hz: int, dur: int):
        """Capture function for scanning: runs wsprd and collects output."""
        from neo_wspr.wspr.decoder import WsprDecoder
        decoder = WsprDecoder()
        wsprd_path = decoder.wsprd_path
        if wsprd_path is None:
            LOG.warning("wsprd not found; skipping live capture for band %s", band_hz)
            return []
        cmd = [wsprd_path]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except Exception:
            LOG.exception("Failed to start wsprd for band %s", band_hz)
            return []

        lines = []
        start = time.time()
        try:
            assert proc.stdout is not None
            while time.time() - start < dur:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                lines.append(line)
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
        return lines

    from neo_wspr.wspr import scan as wspr_scan
    reports = wspr_scan.scan_bands(bands, _capture_fn, duration)

    # Emit JSON if requested, otherwise human-readable logs
    if getattr(args, "json", False):
        print(json.dumps(reports, indent=2, default=str))
        return 0

    # Print ranked report
    for r in reports:
        LOG.info(
            "Band %s: decodes=%s dec/min=%.2f median_snr=%s max_snr=%s unique_calls=%s",
            r.get("band_hz"),
            r.get("band_decodes"),
            r.get("decodes_per_min", 0.0),
            r.get("median_snr_db"),
            r.get("max_snr_db"),
            r.get("unique_calls"),
        )
    return 0

