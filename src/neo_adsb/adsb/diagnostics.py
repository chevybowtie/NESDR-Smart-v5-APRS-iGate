"""ADS-B diagnostics helpers.

This module provides diagnostic checks for ADS-B functionality:
- readsb/dump1090 installation and status
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
    """Check if readsb or dump1090 is installed (prefer readsb)."""
    # Prefer readsb
    readsb = shutil.which("readsb")
    if readsb:
        return DiagnosticResult(
            name="decoder",
            status="OK",
            message="readsb is installed",
            details={"path": readsb, "variant": "readsb"},
        )

    # Alternatives
    dump1090_fa = shutil.which("dump1090-fa")
    if dump1090_fa:
        return DiagnosticResult(
            name="decoder",
            status="OK",
            message="dump1090-fa is installed",
            details={"path": dump1090_fa, "variant": "dump1090-fa"},
        )

    dump1090_mut = shutil.which("dump1090-mutability")
    if dump1090_mut:
        return DiagnosticResult(
            name="decoder",
            status="OK",
            message="dump1090-mutability is installed",
            details={"path": dump1090_mut, "variant": "dump1090-mutability"},
        )

    dump1090 = shutil.which("dump1090")
    if dump1090:
        return DiagnosticResult(
            name="decoder",
            status="OK",
            message="dump1090 is installed",
            details={"path": dump1090, "variant": "dump1090"},
        )

    return DiagnosticResult(
        name="decoder",
        status="ERROR",
        message="No ADS-B decoder found (readsb or dump1090)",
        details={
            "install_hint": "Install readsb (recommended): https://github.com/wiedehopf/adsb-scripts/wiki/Automatic-installation-for-readsb",
            "alternatives": ["dump1090-fa", "dump1090-mutability", "dump1090"],
        },
    )


def check_dump1090_running() -> DiagnosticResult:
    """Check if readsb/dump1090 service is running (prefer readsb)."""
    services = [
        "readsb",
        "dump1090-fa",
        "dump1090",
        "dump1090-mutability",
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

    # Check if there's a service in failure state (hint at root cause)
    failure_details = {
        "checked_services": services,
        "hint": "Enable and start readsb: sudo systemctl enable --now readsb",
    }
    
    # Check if readsb is in failure state and check logs
    try:
        result = subprocess.run(
            ["systemctl", "show", "readsb", "-p", "Result", "-p", "UnitFileState"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "Result=failure" in result.stdout or "Result=exit-code" in result.stdout:
            failure_details["probe_status"] = "Service is failing to start"
            failure_details["hint"] = (
                "Service is crashing on startup. Possible causes:\n"
                "  1. RTL-SDR device not connected (try different USB ports)\n"
                "  2. Device is in use by another process\n"
                "  3. Check with: rtl_test -t, lsusb, or systemctl status readsb"
            )
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return DiagnosticResult(
        name="decoder_service",
        status="ERROR",
        message="No ADS-B decoder service is running",
        details=failure_details,
    )


def check_dump1090_json(
    json_path: str | Path = "/run/readsb/aircraft.json",
) -> DiagnosticResult:
    """Check if decoder JSON output is available and valid (prefer readsb)."""
    path = Path(json_path)
    default_paths = [
        "/run/readsb/aircraft.json",
        "/run/dump1090-fa/aircraft.json",
        "/run/dump1090/aircraft.json",
        "/run/dump1090-mutability/aircraft.json",
    ]
    using_default = str(json_path) in default_paths

    if not path.exists():
        # Only check alternative paths if user didn't specify a custom path
        if using_default:
            alt_paths = [Path(p) for p in default_paths if p != str(json_path)]
            for alt_path in alt_paths:
                if alt_path.exists():
                    path = alt_path
                    break
            else:
                return DiagnosticResult(
                    name="dump1090_json",
                    status="ERROR",
                    message="aircraft.json not found",
                    details={
                        "checked_paths": [str(json_path)] + [str(p) for p in alt_paths],
                        "hint": "Ensure readsb or dump1090 is running",
                    },
                )
        else:
            # Custom path specified but doesn't exist
            return DiagnosticResult(
                name="dump1090_json",
                status="ERROR",
                message="aircraft.json not found",
                details={
                    "path": str(json_path),
                    "hint": "Check the specified path or ensure decoder is running",
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
            message=f"aircraft.json available with {aircraft_count} aircraft",
            details={
                "path": str(path),
                "aircraft_count": aircraft_count,
                "timestamp": now_timestamp,
            },
        )
    except json.JSONDecodeError as exc:
        return DiagnosticResult(
            name="decoder_json",
            status="ERROR",
            message=f"Invalid JSON in decoder output: {exc}",
            details={"path": str(path)},
        )
    except OSError as exc:
        return DiagnosticResult(
            name="decoder_json",
            status="ERROR",
            message=f"Cannot read decoder JSON: {exc}",
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
            # Check if device appears via lsusb (may need permissions)
            lsusb_info = _check_lsusb_for_rtl()
            
            if lsusb_info:
                # Device is in lsusb but rtl_test can't access it
                return DiagnosticResult(
                    name="rtl_sdr",
                    status="WARNING",
                    message="RTL-SDR device found but not accessible (may be in use)",
                    details={
                        "lsusb": lsusb_info,
                        "hint": "Device appears in lsusb but rtl_test cannot access it.\n"
                        "  Likely causes:\n"
                        "  1. Device is in use by dump1090/readsb (expected)\n"
                        "  2. Need to run with sudo or adjust USB permissions",
                    },
                )
            else:
                # Device not found anywhere
                return DiagnosticResult(
                    name="rtl_sdr",
                    status="ERROR",
                    message="No RTL-SDR device found",
                    details={
                        "output": output[:200],
                        "hint": "RTL-SDR device not detected.\n"
                        "  Troubleshooting steps:\n"
                        "  1. Check physical connection to USB port\n"
                        "  2. Try different USB ports (especially root hub ports)\n"
                        "  3. Run 'lsusb' to see if device appears there\n"
                        "  4. Check dmesg for device enumeration messages:\n"
                        "     sudo dmesg | tail -30",
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


def _check_lsusb_for_rtl() -> str | None:
    """Check if RTL-SDR device appears in lsusb output.
    
    Returns device info if found, None otherwise.
    """
    lsusb = shutil.which("lsusb")
    if not lsusb:
        return None
    
    try:
        result = subprocess.run(
            ["lsusb"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout
        
        # Look for common RTL-SDR USB IDs
        # RTL2832U common IDs: 0bda:2832
        # Nooelec Smart: often appears with vendor-specific IDs
        rtl_patterns = ["2832", "RTL", "NESDR", "DVB"]
        
        for line in output.split("\n"):
            if any(pattern in line for pattern in rtl_patterns):
                return line.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    return None


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


def check_readsb_config() -> DiagnosticResult:
    """Check readsb configuration for common issues.
    
    Validates:
    - Device addressing (serial number vs index)
    - Gain settings (auto vs fixed)
    """
    config_path = Path("/etc/default/readsb")
    if not config_path.exists():
        return DiagnosticResult(
            name="readsb_config",
            status="OK",
            message="No readsb config found (using defaults)",
            details={},
        )

    try:
        config_content = config_path.read_text()
        details: dict[str, Any] = {"issues": []}
        status = "OK"

        # Check for device indexing (fragile) vs serial number (robust)
        if "--device 0" in config_content or "--device 1" in config_content:
            details["issues"].append(
                "Using device index (--device 0/1) instead of serial number. "
                "Device indexing is fragile and breaks after USB re-enumeration or thermal events. "
                "Use --device=<SERIAL> instead (e.g., --device=67411606)."
            )
            status = "WARNING"
        elif "--device=" in config_content and "'--device=" not in config_content:
            # Likely using serial number, extract it for validation
            for line in config_content.split("\n"):
                if "--device=" in line:
                    details["device_addressing"] = "serial_number (robust)"
                    break

        # Check for gain auto (can cause thermal issues on RTL-SDR)
        if "--gain auto" in config_content or "--gain auto-verbose" in config_content:
            details["issues"].append(
                "Using auto gain (--gain auto) which can cause excessive power draw and thermal issues. "
                "Consider fixed gain for stability: --gain 35 or --gain 40 (typical values 20-48)."
            )
            status = "WARNING"
        elif "--gain" in config_content:
            for line in config_content.split("\n"):
                if "--gain" in line and "=" in line:
                    gain_val = line.split("--gain")[-1].split()[0]
                    details["gain_setting"] = gain_val
                    break

        if not details["issues"]:
            return DiagnosticResult(
                name="readsb_config",
                status="OK",
                message="readsb config looks good",
                details=details,
            )
        else:
            return DiagnosticResult(
                name="readsb_config",
                status=status,
                message=f"readsb config: {len(details['issues'])} issue(s) found",
                details=details,
            )

    except OSError as exc:
        return DiagnosticResult(
            name="readsb_config",
            status="WARNING",
            message=f"Cannot read readsb config: {exc}",
            details={},
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
    report.checks.append(check_readsb_config())
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
