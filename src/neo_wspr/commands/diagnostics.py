"""WSPR diagnostics command implementation.

Runs upconverter detection heuristics.
"""

from __future__ import annotations

import logging
from argparse import Namespace

from neo_core import config as config_module
from neo_core.diagnostics_helpers import check_disk_space

LOG = logging.getLogger(__name__)


def run_diagnostics(args: Namespace) -> int:
    """Run WSPR-specific diagnostics (upconverter detection)."""
    cfg_path = getattr(args, "config", None)
    try:
        if cfg_path:
            config_module.load_config(cfg_path)
        else:
            config_module.load_config()
    except Exception:
        LOG.debug("No configuration available")

    LOG.info("Requested WSPR diagnostics")
    data_dir = config_module.get_mode_data_dir("wspr")

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

    # HARDENING.md #10: surface low free-space as a health signal, since it
    # matters more than raw connectivity for a months-long unattended run.
    disk = check_disk_space(data_dir)
    if disk.status == "ok":
        LOG.info("Disk space: %s", disk.message)
    else:
        LOG.warning("Disk space: %s", disk.message)

    # Emit JSON if requested
    if getattr(args, "json", False):
        import json

        result = {
            "upconverter_hint": hint,
            "spots_analyzed": len(spots),
            "disk_space": {
                "status": disk.status,
                "message": disk.message,
                "details": disk.details,
            },
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"Disk space: {disk.message}")

    return 1 if disk.status == "error" else 0
