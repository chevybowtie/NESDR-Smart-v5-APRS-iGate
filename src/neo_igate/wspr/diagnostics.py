"""Upconverter and SDR diagnostics for WSPR (skeleton).

Provides heuristics for detecting an upconverter and recommending an LO
offset. Since passive upconverters aren't USB devices, heuristics will rely
on spectral analysis and user-assisted checks. This module contains stubs
to be implemented during feature development.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable
from statistics import median

LOG = logging.getLogger(__name__)


def detect_upconverter_hint(spots: Iterable[dict] | None = None) -> Dict[str, object]:
    """Return a heuristic result for upconverter detection.

    If `spots` is provided (an iterable of spot dicts with `freq_hz` values)
    the heuristic compares the median observed frequency against a set of
    expected WSPR band center frequencies and, if a substantial offset is
    present, returns a recommended LO offset and a confidence score.

    The returned dict includes a `confidence` 0..1 and optional
    `recommended_lo_offset_hz` when a likely offset is detected.
    """
    LOG.debug("Running upconverter detection heuristic")

    # Common nominal WSPR frequencies (Hz) for heuristic matching
    nominal_centers = [
        3_572_000,  # 80m
        5_290_000,  # 60m
        7_040_000,  # 40m
        10_140_000,  # 30m
        14_080_000,  # 20m
        18_110_000,  # 17m
        21_080_000,  # 15m
        28_080_000,  # 10m
    ]

    if not spots:
        return {"confidence": 0.0, "recommended_lo_offset_hz": None}

    freqs = []
    for s in spots:
        try:
            f = float(s.get("freq_hz"))
        except Exception:
            continue
        freqs.append(f)

    if not freqs:
        return {"confidence": 0.0, "recommended_lo_offset_hz": None}

    med = median(freqs)
    # find nearest nominal center
    nearest = min(nominal_centers, key=lambda c: abs(c - med))
    diff = med - nearest

    # heuristic thresholds: if offset > 50 kHz, this may indicate an upconverter
    threshold = 50_000
    confidence = min(1.0, abs(diff) / 500_000)
    if abs(diff) >= threshold:
        return {"confidence": confidence, "recommended_lo_offset_hz": int(-diff)}
    return {"confidence": 0.0, "recommended_lo_offset_hz": None}
