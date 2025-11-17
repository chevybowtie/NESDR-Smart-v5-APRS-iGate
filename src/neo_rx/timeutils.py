"""Small time utilities used by CLI and helpers.

This module provides a single helper for producing timezone-aware UTC
timestamps formatted as YYYYMMDDTHHMMSSZ.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_timestamp() -> str:
    """Return current UTC time formatted as YYYYMMDDTHHMMSSZ.

    Using a timezone-aware `datetime` avoids deprecation warnings.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
