"""Calibration helpers for WSPR (skeleton).

Includes ppm calculation helpers and plumbing to apply frequency corrections
via the radio driver. Currently a minimal placeholder.
"""

from __future__ import annotations

import logging
from typing import Optional

LOG = logging.getLogger(__name__)


def compute_ppm_from_offset(freq_hz: float, offset_hz: float) -> float:
    """Compute parts-per-million correction given an offset in Hz."""
    if freq_hz == 0:
        raise ValueError("freq_hz must be non-zero")
    ppm = (offset_hz / freq_hz) * 1_000_000.0
    LOG.debug("Computed ppm=%s from freq=%s offset=%s", ppm, freq_hz, offset_hz)
    return ppm


def apply_ppm_to_radio(ppm: float) -> None:
    """Apply ppm correction to the radio driver (requires implementation)."""
    LOG.info("Applying ppm correction (stub): %s", ppm)
