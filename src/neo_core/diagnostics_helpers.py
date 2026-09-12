"""Shared helpers for connectivity and resource diagnostics.

This module was migrated from neo_rx.diagnostics_helpers.
"""

from __future__ import annotations

import os
import shutil
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


# Free-space thresholds (percent free) below which `check_disk_space` reports
# a warning/error. Long-running deployments accumulate rotated logs and
# JSON-lines capture files, so running low on space is a more likely failure
# mode than most connectivity issues once a station has been up for months
# (see HARDENING.md item 10). Overridable per-deployment via env vars.
DISK_WARN_PERCENT_ENV_VAR = "NEO_RX_DISK_WARN_PERCENT_FREE"
DISK_ERROR_PERCENT_ENV_VAR = "NEO_RX_DISK_ERROR_PERCENT_FREE"
DEFAULT_DISK_WARN_PERCENT_FREE = 10.0
DEFAULT_DISK_ERROR_PERCENT_FREE = 3.0


@dataclass(slots=True)
class DiskSpaceResult:
    """Represents the outcome of a free-disk-space check."""

    status: str  # "ok" | "warning" | "error"
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def _resolve_percent_threshold(env_var: str, default: float) -> float:
    raw = os.environ.get(env_var)
    if raw:
        try:
            value = float(raw.strip())
        except ValueError:
            value = -1.0
        if 0.0 < value < 100.0:
            return value
    return default


def check_disk_space(
    path: str | Path,
    *,
    warn_percent_free: float | None = None,
    error_percent_free: float | None = None,
) -> DiskSpaceResult:
    """Check free disk space on the filesystem containing `path`.

    Thresholds default to 10% (warning) / 3% (error) free and can be
    overridden per call or via `NEO_RX_DISK_WARN_PERCENT_FREE` /
    `NEO_RX_DISK_ERROR_PERCENT_FREE`.
    """
    warn_threshold = (
        warn_percent_free
        if warn_percent_free is not None
        else _resolve_percent_threshold(
            DISK_WARN_PERCENT_ENV_VAR, DEFAULT_DISK_WARN_PERCENT_FREE
        )
    )
    error_threshold = (
        error_percent_free
        if error_percent_free is not None
        else _resolve_percent_threshold(
            DISK_ERROR_PERCENT_ENV_VAR, DEFAULT_DISK_ERROR_PERCENT_FREE
        )
    )

    target = Path(path)
    probe = target
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent

    try:
        usage = shutil.disk_usage(probe)
    except OSError as exc:
        return DiskSpaceResult(
            status="warning",
            message=f"Could not determine free disk space for {target}: {exc}",
            details={"path": str(target)},
        )

    percent_free = (usage.free / usage.total * 100) if usage.total else 100.0
    details = {
        "path": str(target),
        "total_bytes": usage.total,
        "free_bytes": usage.free,
        "percent_free": round(percent_free, 1),
    }

    if percent_free <= error_threshold:
        status = "error"
    elif percent_free <= warn_threshold:
        status = "warning"
    else:
        status = "ok"

    message = f"{percent_free:.1f}% free on {target}"
    if status != "ok":
        threshold = error_threshold if status == "error" else warn_threshold
        message += f" (below {threshold:.0f}% {status} threshold)"

    return DiskSpaceResult(status=status, message=message, details=details)
