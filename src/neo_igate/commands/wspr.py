"""CLI command handler for WSPR operations (skeleton).

Provides a single entrypoint `run_wspr` used by `neo-igate wspr`.
"""

from __future__ import annotations

import logging
from argparse import Namespace

LOG = logging.getLogger(__name__)


def run_wspr(args: Namespace) -> int:
    """Handle top-level `wspr` CLI invocations.

    Currently this function is a lightweight dispatcher that logs the
    requested action. Later it will orchestrate capture, decode, diagnostics,
    calibration, and upload flows.
    """
    if getattr(args, "start", False):
        LOG.info("Requested WSPR start (stub)")
        return 0
    if getattr(args, "scan", False):
        LOG.info("Requested WSPR band-scan (stub)")
        return 0
    if getattr(args, "diagnostics", False):
        LOG.info("Requested WSPR diagnostics (stub)")
        return 0
    if getattr(args, "calibrate", False):
        LOG.info("Requested WSPR calibration (stub)")
        return 0
    if getattr(args, "upload", False):
        LOG.info("Requested WSPR upload (stub)")
        return 0

    LOG.info("No action specified for wspr; nothing to do")
    return 0


__all__ = ["run_wspr"]
