"""Back-compat shim re-exporting from neo_wspr.wspr.diagnostics."""

from neo_wspr.wspr.diagnostics import *  # noqa: F401,F403


import logging
from typing import Dict, Iterable
from statistics import median

LOG = logging.getLogger(__name__)


def detect_upconverter_hint(spots: Iterable[dict] | None = None) -> Dict[str, object]:
    """Return a heuristic result for upconverter detection.

    If `spots` is provided (an iterable of spot dicts with `freq_hz` and optional
    `snr_db` values), the heuristic compares the median observed frequency against
    a set of expected WSPR band center frequencies. If a substantial offset is
    present, returns a recommended LO offset and a confidence score.

    Additional heuristics consider SNR distribution (upconverter may affect noise
    floor or gain characteristics).

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

    spots_list = list(spots)  # Consume iterable once
    freqs = []
    snrs = []
    for s in spots_list:
        try:
            f = float(s.get("freq_hz"))
            freqs.append(f)
        except Exception:
            continue
        try:
            snr = float(s.get("snr_db"))
            snrs.append(snr)
        except Exception:
            pass

    if not freqs:
        return {"confidence": 0.0, "recommended_lo_offset_hz": None}

    med_freq = median(freqs)
    # Find nearest nominal center
    nearest = min(nominal_centers, key=lambda c: abs(c - med_freq))
    freq_offset = med_freq - nearest

    # Heuristic thresholds: if offset > 50 kHz, this may indicate an upconverter
    freq_threshold = 50_000
    freq_confidence = min(1.0, abs(freq_offset) / 500_000)

    # SNR-based heuristic: if distribution is unusual (e.g., consistently degraded),
    # this may indicate a converter impacting noise floor
    snr_confidence = 0.0
    if snrs:
        mean_snr = sum(snrs) / len(snrs)
        # Typical SNR for WSPR is -20 to -5 dB; if consistently lower, may indicate
        # upconverter reducing signal (or external LNA boosting).
        # This is a soft indicator (confidence 0.2 max) since many factors affect SNR.
        if mean_snr < -25:
            snr_confidence = 0.2
        elif mean_snr > 0:
            # Unusually high SNR might indicate LNA in converter
            snr_confidence = 0.1

    # Combine heuristics
    combined_confidence = min(1.0, freq_confidence + snr_confidence)

    if abs(freq_offset) >= freq_threshold:
        return {
            "confidence": combined_confidence,
            "recommended_lo_offset_hz": int(-freq_offset),
            "freq_offset_hz": int(freq_offset),
            "median_freq_hz": int(med_freq),
            "nominal_center_hz": nearest,
            "mean_snr_db": round(sum(snrs) / len(snrs), 2) if snrs else None,
        }
    return {
        "confidence": 0.0,
        "recommended_lo_offset_hz": None,
        "freq_offset_hz": int(freq_offset) if freq_offset else None,
        "median_freq_hz": int(med_freq),
        "nominal_center_hz": nearest,
        "mean_snr_db": round(sum(snrs) / len(snrs), 2) if snrs else None,
    }
