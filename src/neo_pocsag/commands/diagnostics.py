"""POCSAG diagnostics command."""

from __future__ import annotations

import logging
from argparse import Namespace

from neo_pocsag.pocsag.diagnostics import run_diagnostics

LOG = logging.getLogger(__name__)


def run_diagnostics_command(args: Namespace) -> int:
    """Run POCSAG diagnostics and display results."""
    print("Running POCSAG diagnostics...\n")

    report = run_diagnostics()

    for check in report.checks:
        status_icon = {
            "OK": "✓",
            "WARNING": "⚠",
            "ERROR": "✗",
        }.get(check.status, "?")
        print(f"{status_icon} {check.name}: {check.message}")
        if check.details:
            for key, value in check.details.items():
                print(f"  {key}: {value}")

    print(f"\nOverall: {'PASS' if report.ok else 'FAIL'}")
    return 0 if report.ok else 1