"""APRS diagnostics command wrapper.

Delegates to the legacy neo_rx CLI diagnostics implementation during migration.
"""

from __future__ import annotations

from argparse import Namespace
from typing import List


def run_diagnostics(args: Namespace) -> int:
    """Run APRS diagnostics via the legacy CLI, mapping known flags."""
    # Lazy import avoids pulling heavy deps at module import time
    from neo_rx.cli import main as legacy_main  # type: ignore[import]

    argv: List[str] = ["diagnostics"]

    config = getattr(args, "config", None)
    if config:
        argv += ["--config", str(config)]

    if getattr(args, "json", False):
        argv.append("--json")

    if getattr(args, "verbose", False):
        argv.append("--verbose")

    return legacy_main(argv)
