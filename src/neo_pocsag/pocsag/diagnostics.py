"""POCSAG diagnostics helpers.

This module provides diagnostic checks for POCSAG functionality:
- multimon-ng installation and status
- RTL-SDR availability for POCSAG frequencies
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)


@dataclass
class DiagnosticResult:
    """Result of a single diagnostic check."""

    name: str
    status: str  # "OK", "WARNING", "ERROR"
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticsReport:
    """Complete diagnostics report for POCSAG functionality."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    checks: list[DiagnosticResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if all checks passed."""
        return all(c.status == "OK" for c in self.checks)

    @property
    def has_errors(self) -> bool:
        """Return True if any check has ERROR status."""
        return any(c.status == "ERROR" for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "checks": [c.__dict__ for c in self.checks],
            "ok": self.ok,
            "has_errors": self.has_errors,
        }


def run_diagnostics() -> DiagnosticsReport:
    """Run all POCSAG diagnostics and return a report."""
    report = DiagnosticsReport()

    # Check multimon-ng installation
    report.checks.append(_check_multimon_ng())

    # Check RTL-SDR
    report.checks.append(_check_rtl_sdr())

    return report


def _check_multimon_ng() -> DiagnosticResult:
    """Check if multimon-ng is installed and working."""
    if not shutil.which("multimon-ng"):
        return DiagnosticResult(
            name="multimon_ng",
            status="ERROR",
            message="multimon-ng not found in PATH",
            details={"suggestion": "Install multimon-ng: apt-get install multimon-ng"},
        )

    # Test multimon-ng with --help
    try:
        result = subprocess.run(
            ["multimon-ng", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        combined_output = result.stdout + result.stderr
        if "POCSAG" in combined_output:
            return DiagnosticResult(
                name="multimon_ng",
                status="OK",
                message="multimon-ng installed and supports POCSAG",
            )
        else:
            return DiagnosticResult(
                name="multimon_ng",
                status="WARNING",
                message="multimon-ng installed but POCSAG support unclear",
            )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return DiagnosticResult(
            name="multimon_ng",
            status="ERROR",
            message=f"multimon-ng test failed: {exc}",
        )


def _check_rtl_sdr() -> DiagnosticResult:
    """Check if RTL-SDR is available."""
    if not shutil.which("rtl_test"):
        return DiagnosticResult(
            name="rtl_sdr",
            status="ERROR",
            message="rtl_test not found in PATH",
            details={"suggestion": "Install rtl-sdr: apt-get install rtl-sdr"},
        )

    # Quick test of RTL-SDR
    try:
        result = subprocess.run(
            ["rtl_test", "-t"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return DiagnosticResult(
                name="rtl_sdr",
                status="OK",
                message="RTL-SDR detected and working",
            )
        else:
            return DiagnosticResult(
                name="rtl_sdr",
                status="WARNING",
                message="RTL-SDR test inconclusive",
                details={"output": result.stderr.strip()},
            )
    except subprocess.TimeoutExpired:
        return DiagnosticResult(
            name="rtl_sdr",
            status="ERROR",
            message="RTL-SDR test timed out",
        )
    except OSError as exc:
        return DiagnosticResult(
            name="rtl_sdr",
            status="ERROR",
            message=f"RTL-SDR test failed: {exc}",
        )