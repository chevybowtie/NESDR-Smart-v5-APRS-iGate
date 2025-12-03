"""ADS-B diagnostics command implementation.

Run diagnostic checks for ADS-B functionality.
"""

from __future__ import annotations

import json
import logging
from argparse import Namespace

from neo_adsb.adsb.diagnostics import run_diagnostics

LOG = logging.getLogger(__name__)


def run_diagnostics_cmd(args: Namespace) -> int:
    """Run ADS-B diagnostics and display results."""
    json_path = getattr(args, "json_path", None)
    check_adsbexchange = not getattr(args, "no_adsbexchange", False)
    output_json = getattr(args, "json", False)
    verbose = getattr(args, "verbose", False)

    LOG.info("Running ADS-B diagnostics...")

    report = run_diagnostics(
        check_adsbexchange=check_adsbexchange,
        json_path=json_path,
    )

    if output_json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.ok else 1

    # Text output
    print("\nADS-B Diagnostics Report")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Status: {_colorize_status(report.to_dict()['status'])}")
    print("-" * 60)

    for check in report.checks:
        status_str = _colorize_status(check.status)
        print(f"\n{check.name}: {status_str}")
        print(f"  {check.message}")

        # Always show installation hints for errors/warnings
        if check.details:
            hint = check.details.get("install_hint") or check.details.get("hint")
            if hint and check.status != "OK":
                print(f"  → {hint}")

        # Show all details in verbose mode
        if verbose and check.details:
            for key, value in check.details.items():
                # Skip hints in verbose since we already showed them
                if key in ("install_hint", "hint"):
                    continue
                if isinstance(value, dict):
                    print(f"    {key}:")
                    for k, v in value.items():
                        print(f"      {k}: {v}")
                else:
                    print(f"    {key}: {value}")

    print("\n" + "=" * 60)
    if report.ok:
        print("All checks passed!")
    elif report.has_errors:
        print("Some checks failed. See details above.")
    else:
        print("Some warnings detected. See details above.")

    return 0 if report.ok else 1


def _colorize_status(status: str) -> str:
    """Add ANSI color codes to status string."""
    colors = {
        "OK": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
    }
    reset = "\033[0m"
    color = colors.get(status, "")
    return f"{color}{status}{reset}"
