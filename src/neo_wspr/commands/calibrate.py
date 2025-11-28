"""WSPR calibrate command implementation.

Estimates PPM offset from decoded spots.
"""

from __future__ import annotations

import logging
from argparse import Namespace
from pathlib import Path

from neo_core import config as config_module

LOG = logging.getLogger(__name__)


def run_calibrate(args: Namespace) -> int:
    """Run WSPR calibration: estimate PPM offset from known-good spots."""
    cfg_path = getattr(args, "config", None)
    cfg = None
    try:
        if cfg_path:
            cfg = config_module.load_config(cfg_path)
        else:
            cfg = config_module.load_config()
    except Exception:
        LOG.debug("No configuration available")

    LOG.info("Requested WSPR calibration")
    data_dir = config_module.get_mode_data_dir("wspr")

    from neo_wspr.wspr.calibrate import (
        load_spots_from_jsonl,
        estimate_offset_from_spots,
    )

    # Determine spots file: CLI override -> config data dir
    spots_path = None
    if getattr(args, "samples", None):
        spots_path = Path(getattr(args, "samples"))
    else:
        spots_path = data_dir / "wspr_spots.jsonl"

    spots = load_spots_from_jsonl(spots_path)
    if not spots:
        LOG.warning("No spots found in %s; cannot calibrate", spots_path)
        return 1

    # Expected frequency: CLI override > config first band (if present)
    expected_freq = None
    band_str = getattr(args, "band", None)
    if band_str:
        band_mapping = {
            "80m": 3_594_000,
            "40m": 7_038_600,
            "30m": 10_140_200,
            "20m": 14_095_600,
            "10m": 28_124_600,
            "6m": 50_294_800,
            "2m": 144_489_000,
            "70cm": 432_500_000,
        }
        expected_freq = band_mapping.get(band_str)
    elif cfg and getattr(cfg, "wspr_bands_hz", None):
        expected_freq = cfg.wspr_bands_hz[0]

    try:
        result = estimate_offset_from_spots(spots, expected_freq)
    except Exception:
        LOG.exception("Failed to estimate offset from spots")
        return 1

    LOG.info(
        "Calibration result: median_obs=%.0f Hz offset=%.1f Hz ppm=%.3f count=%d",
        result.get("median_observed_freq_hz", 0.0),
        result.get("offset_hz", 0.0),
        result.get("ppm", 0.0),
        result.get("count", 0),
    )

    # Note: --apply flag not currently exposed in unified CLI; reserved for future
    # If needed, can add via: if getattr(args, "apply", False)
    ppm = result.get("ppm", 0.0)
    LOG.info(
        "To apply this correction, add ppm_correction = %.3f to your config.toml", ppm
    )

    return 0
