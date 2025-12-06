"""Frequency scanning utilities for POCSAG.

Provides scanning functionality to sweep through frequency ranges
and detect POCSAG pager activity.
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable, List

from .capture import PocsagMessage

LOG = logging.getLogger(__name__)

CaptureFunc = Callable[[int, int], Iterable[PocsagMessage]]


def score_frequency(messages: List[PocsagMessage], duration_s: int) -> dict:
    """Compute scoring metrics for a single frequency given parsed messages.

    Returns a dict with keys: `message_count`, `messages_per_min`, `unique_addresses`.
    """
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")

    message_count = len(messages)
    messages_per_min = message_count / (duration_s / 60.0)
    unique_addresses = len({msg.address for msg in messages})

    return {
        "message_count": message_count,
        "messages_per_min": messages_per_min,
        "unique_addresses": unique_addresses,
    }


def scan_frequencies(
    frequencies_hz: List[int], capture_fn: CaptureFunc, duration_s: int
) -> List[dict]:
    """Scan the provided frequencies and return a list of frequency reports.

    Each report contains the `frequency_hz` and the metrics returned by
    `score_frequency`. Frequencies are returned in descending order by `messages_per_min`.
    """
    if not frequencies_hz:
        return []

    reports: List[dict] = []

    for freq in frequencies_hz:
        LOG.info("Scanning frequency %s Hz for %ss", freq, duration_s)
        try:
            messages = list(capture_fn(freq, duration_s))
        except Exception:
            LOG.exception("capture_fn failed for frequency %s", freq)
            messages = []

        metrics = score_frequency(messages, duration_s)
        report = {"frequency_hz": freq, **metrics}
        reports.append(report)

    # sort by messages_per_min desc
    reports.sort(key=lambda r: r.get("messages_per_min", 0), reverse=True)
    return reports