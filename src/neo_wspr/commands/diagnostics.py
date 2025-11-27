"""WSPR diagnostics command implementation.

Runs upconverter detection heuristics.
"""

from __future__ import annotations

import logging
from argparse import Namespace

from neo_core import config as config_module

LOG = logging.getLogger(__name__)


def run_diagnostics(args: Namespace) -> int:
    """Run WSPR-specific diagnostics (upconverter detection)."""
    cfg_path = getattr(args, "config", None)
    cfg = None
    try:
        if cfg_path:
            cfg = config_module.load_config(cfg_path)
        else:
            cfg = config_module.load_config()
    except Exception:
        LOG.debug("No configuration available")

    LOG.info("Requested WSPR diagnostics")
    data_dir = config_module.get_data_dir() / "wspr"

    from neo_wspr.wspr import diagnostics as wspr_diag
    from neo_wspr.wspr.calibrate import load_spots_from_jsonl

    # Attempt to load recent spots from data dir (best-effort)
    spots_file = data_dir / "wspr_spots.jsonl"
    spots = []
    try:
        spots = load_spots_from_jsonl(spots_file)
    except Exception:
        LOG.debug("Failed to load spots for diagnostics; proceeding without spot data")

    hint = wspr_diag.detect_upconverter_hint(spots)
    LOG.info("Upconverter diagnostic: %s", hint)

    # Emit JSON if requested
    if getattr(args, "json", False):
        import json
        result = {
            "upconverter_hint": hint,
            "spots_analyzed": len(spots),
        }
        print(json.dumps(result, indent=2))

    return 0

