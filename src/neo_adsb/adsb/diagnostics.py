"""ADS-B diagnostics helpers.

This module provides diagnostic checks for ADS-B functionality:
- dump1090/readsb installation and status
- ADS-B Exchange feedclient status
- RTL-SDR availability for 1090 MHz
"""

from __future__ import annotations

import json
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
    """Complete diagnostics report for ADS-B functionality."""

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
            "status": "OK" if self.ok else ("ERROR" if self.has_errors else "WARNING"),
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "details": c.details,
                }
                for c in self.checks
            ],
        }


def check_dump1090_installed() -> DiagnosticResult:
    """Check if dump1090 or readsb is installed."""
    # Check for dump1090-fa (FlightAware version)
    dump1090_fa = shutil.which("dump1090-fa")
    if dump1090_fa:
        return DiagnosticResult(
            name="dump1090",
            status="OK",
            message="dump1090-fa is installed",
            details={"path": dump1090_fa, "variant": "dump1090-fa"},
        )

    # Check for dump1090-mutability
    dump1090_mut = shutil.which("dump1090-mutability")
    if dump1090_mut:
        return DiagnosticResult(
            name="dump1090",
            status="OK",
            message="dump1090-mutability is installed",
            details={"path": dump1090_mut, "variant": "dump1090-mutability"},
        )

    # Check for readsb
    readsb = shutil.which("readsb")
    if readsb:
        return DiagnosticResult(
            name="dump1090",
            status="OK",
            message="readsb is installed",
            details={"path": readsb, "variant": "readsb"},
        )

    # Check for generic dump1090
    dump1090 = shutil.which("dump1090")
    if dump1090:
        return DiagnosticResult(
            name="dump1090",
            status="OK",
            message="dump1090 is installed",
            details={"path": dump1090, "variant": "dump1090"},
        )

    return DiagnosticResult(
        name="dump1090",
        status="ERROR",
        message="No dump1090/readsb decoder found",
        details={
            "install_hint": "Install dump1090-fa: sudo apt install dump1090-fa"
        },
    )


def check_dump1090_running() -> DiagnosticResult:
    """Check if dump1090/readsb service is running."""
    services = [
        "dump1090-fa",
        "dump1090",
        "dump1090-mutability",
        "readsb",
    ]

    for service in services:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return DiagnosticResult(
                    name="dump1090_service",
                    status="OK",
                    message=f"{service} service is running",
                    details={"service": service, "state": "active"},
                )
        except (subprocess.SubprocessError, FileNotFoundError):
            continue

    return DiagnosticResult(
        name="dump1090_service",
        status="ERROR",
        message="No dump1090/readsb service is running",
        details={
            "checked_services": services,
            "hint": "Start the service: sudo systemctl start dump1090-fa",
        },
    )


def check_dump1090_json(json_path: str | Path = "/run/dump1090-fa/aircraft.json") -> DiagnosticResult:
    """Check if dump1090 JSON output is available and valid."""
    path = Path(json_path)

    if not path.exists():
        # Check alternative paths
        alt_paths = [
            Path("/run/dump1090/aircraft.json"),
            Path("/run/readsb/aircraft.json"),
            Path("/run/dump1090-mutability/aircraft.json"),
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                path = alt_path
                break
        else:
            return DiagnosticResult(
                name="dump1090_json",
                status="ERROR",
                message="dump1090 JSON output not found",
                details={
                    "checked_paths": [str(json_path)] + [str(p) for p in alt_paths],
                    "hint": "Ensure dump1090 service is running and configured correctly",
                },
            )

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        aircraft_count = len(data.get("aircraft", []))
        now_timestamp = data.get("now", 0)

        return DiagnosticResult(
            name="dump1090_json",
            status="OK",
            message=f"dump1090 JSON available with {aircraft_count} aircraft",
            details={
                "path": str(path),
                "aircraft_count": aircraft_count,
                "timestamp": now_timestamp,
            },
        )
    except json.JSONDecodeError as exc:
        return DiagnosticResult(
            name="dump1090_json",
            status="ERROR",
            message=f"Invalid JSON in dump1090 output: {exc}",
            details={"path": str(path)},
        )
    except OSError as exc:
        return DiagnosticResult(
            name="dump1090_json",
            status="ERROR",
            message=f"Cannot read dump1090 JSON: {exc}",
            details={"path": str(path)},
        )


def check_rtl_sdr() -> DiagnosticResult:
    """Check if RTL-SDR is available."""
    rtl_test = shutil.which("rtl_test")
    if not rtl_test:
        return DiagnosticResult(
            name="rtl_sdr",
            status="WARNING",
            message="rtl_test not found; cannot verify SDR availability",
            details={"install_hint": "Install rtl-sdr: sudo apt install rtl-sdr"},
        )

    try:
        # Run rtl_test with timeout to detect device
        result = subprocess.run(
            ["rtl_test", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # rtl_test returns 0 even when finding device, check stderr for device info
        output = result.stdout + result.stderr
        if "Found" in output and "device" in output.lower():
            return DiagnosticResult(
                name="rtl_sdr",
                status="OK",
                message="RTL-SDR device detected",
                details={"output": output[:200]},
            )
        elif "No supported" in output or "No device" in output:
            return DiagnosticResult(
                name="rtl_sdr",
                status="WARNING",
                message="No RTL-SDR device found (may be in use by dump1090)",
                details={
                    "output": output[:200],
                    "hint": "If dump1090 is running, this is expected",
                },
            )
    except subprocess.TimeoutExpired:
        return DiagnosticResult(
            name="rtl_sdr",
            status="WARNING",
            message="RTL-SDR check timed out (device may be in use)",
            details={"hint": "If dump1090 is running, this is expected"},
        )
    except subprocess.SubprocessError as exc:
        return DiagnosticResult(
            name="rtl_sdr",
            status="WARNING",
            message=f"RTL-SDR check failed: {exc}",
            details={},
        )

    return DiagnosticResult(
        name="rtl_sdr",
        status="WARNING",
        message="RTL-SDR status unknown",
        details={},
    )


def check_adsbexchange_installed() -> DiagnosticResult:
    """Check if ADS-B Exchange feedclient is installed."""
    adsbx_path = Path("/usr/local/share/adsbexchange")
    config_path = Path("/etc/default/adsbexchange")

    if adsbx_path.exists() or config_path.exists():
        uuid_path = adsbx_path / "adsbx-uuid"
        uuid = None
        if uuid_path.exists():
            try:
                uuid = uuid_path.read_text().strip()
            except OSError:
                pass

        return DiagnosticResult(
            name="adsbexchange",
            status="OK",
            message="ADS-B Exchange feedclient is installed",
            details={
                "path": str(adsbx_path),
                "config_exists": config_path.exists(),
                "uuid": uuid[:8] + "..." if uuid else None,
            },
        )

    return DiagnosticResult(
        name="adsbexchange",
        status="WARNING",
        message="ADS-B Exchange feedclient not installed",
        details={
            "install_hint": "curl -L -o /tmp/axfeed.sh https://adsbexchange.com/feed.sh && sudo bash /tmp/axfeed.sh"
        },
    )


def check_adsbexchange_services() -> DiagnosticResult:
    """Check if ADS-B Exchange services are running."""
    services = {
        "adsbexchange-feed": False,
        "adsbexchange-mlat": False,
    }

    for service in services:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
                timeout=5,
            )
            services[service] = result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    if all(services.values()):
        return DiagnosticResult(
            name="adsbexchange_services",
            status="OK",
            message="ADS-B Exchange services are running",
            details=services,
        )
    elif any(services.values()):
        return DiagnosticResult(
            name="adsbexchange_services",
            status="WARNING",
            message="Some ADS-B Exchange services not running",
            details={
                **services,
                "hint": "Start services: sudo systemctl start adsbexchange-feed adsbexchange-mlat",
            },
        )
    else:
        return DiagnosticResult(
            name="adsbexchange_services",
            status="WARNING",
            message="ADS-B Exchange services not running",
            details={
                **services,
                "hint": "Start services: sudo systemctl start adsbexchange-feed adsbexchange-mlat",
            },
        )


def run_diagnostics(
    check_adsbexchange: bool = True,
    json_path: str | Path | None = None,
) -> DiagnosticsReport:
    """Run all ADS-B diagnostics checks.

    Args:
        check_adsbexchange: Include ADS-B Exchange checks
        json_path: Custom path to dump1090 aircraft.json

    Returns:
        DiagnosticsReport with all check results
    """
    report = DiagnosticsReport()

    # Core checks
    report.checks.append(check_dump1090_installed())
    report.checks.append(check_dump1090_running())
    if json_path:
        report.checks.append(check_dump1090_json(json_path))
    else:
        report.checks.append(check_dump1090_json())
    report.checks.append(check_rtl_sdr())

    # ADS-B Exchange checks
    if check_adsbexchange:
        report.checks.append(check_adsbexchange_installed())
        report.checks.append(check_adsbexchange_services())

    return report
