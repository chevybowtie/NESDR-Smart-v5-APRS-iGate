"""Upconverter and SDR diagnostics for WSPR (skeleton).

Provides heuristics for detecting an upconverter and recommending an LO
offset. Since passive upconverters aren't USB devices, heuristics will rely
on spectral analysis and user-assisted checks. This module contains stubs
to be implemented during feature development.
"""

from __future__ import annotations

import logging
from typing import Dict

LOG = logging.getLogger(__name__)


def detect_upconverter_hint(sample: bytes | None = None) -> Dict[str, object]:
    """Return a heuristic result for upconverter detection.

    The returned dict includes a `confidence` 0..1 and optional
    `recommended_lo_offset_hz` when a likely offset is detected.
    """
    LOG.debug("Running upconverter detection heuristic (stub)")
    return {"confidence": 0.0, "recommended_lo_offset_hz": None}
