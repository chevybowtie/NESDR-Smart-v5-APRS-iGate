"""Back-compat shim re-exporting from neo_wspr.wspr.scan."""

from neo_wspr.wspr.scan import *  # noqa: F401,F403


import logging
from statistics import median
from typing import Callable, Iterable, List

from .decoder import WsprDecoder

LOG = logging.getLogger(__name__)

CaptureFunc = Callable[[int, int], Iterable[bytes | str]]


def score_band(spots: List[dict], duration_s: int) -> dict:
    """Compute scoring metrics for a single band given parsed spots.

    Returns a dict with keys: `band_decodes`, `decodes_per_min`,
    `median_snr_db`, `max_snr_db`, `unique_calls`.
    """
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")

    band_decodes = len(spots)
    decodes_per_min = band_decodes / (duration_s / 60.0)

    snrs = [s.get("snr_db") for s in spots if s.get("snr_db") is not None]
    median_snr_db = int(median(snrs)) if snrs else None
    max_snr_db = int(max(snrs)) if snrs else None
    unique_calls = len({s.get("call") for s in spots if s.get("call")})

    return {
        "band_decodes": band_decodes,
        "decodes_per_min": decodes_per_min,
        "median_snr_db": median_snr_db,
        "max_snr_db": max_snr_db,
        "unique_calls": unique_calls,
    }


def scan_bands(
    bands_hz: List[int], capture_fn: CaptureFunc, duration_s: int
) -> List[dict]:
    """Scan the provided bands and return a ranked list of band reports.

    Each report contains the `band_hz` and the metrics returned by
    `score_band`. Bands are returned in descending order by `decodes_per_min`.
    """
    if not bands_hz:
        return []

    decoder = WsprDecoder()
    reports: List[dict] = []

    for band in bands_hz:
        LOG.info("Scanning band %s for %ss", band, duration_s)
        try:
            lines = capture_fn(band, duration_s)
        except Exception:
            LOG.exception("capture_fn failed for band %s", band)
            lines = []

        spots = list(decoder.decode_stream(lines))
        metrics = score_band(spots, duration_s)
        report = {"band_hz": band, **metrics}
        reports.append(report)

    # sort by decodes_per_min desc
    reports.sort(key=lambda r: r.get("decodes_per_min", 0), reverse=True)
    return reports
