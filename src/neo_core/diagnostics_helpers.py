"""Shared helpers for connectivity diagnostics.

This module was migrated from neo_rx.diagnostics_helpers.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass


@dataclass(slots=True)
class ConnectivityResult:
    """Represents the outcome of probing a TCP endpoint."""

    success: bool
    latency_ms: float | None = None
    error: str | None = None


def probe_tcp_endpoint(
    host: str, port: int, timeout: float = 1.0
) -> ConnectivityResult:
    """Attempt to connect to a TCP endpoint, returning latency or error information."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = round((time.perf_counter() - start) * 1000, 1)
        return ConnectivityResult(success=True, latency_ms=latency)
    except OSError as exc:
        return ConnectivityResult(success=False, error=str(exc))
