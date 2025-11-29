"""APRS setup command wrapper.

Delegates to the legacy neo_rx CLI setup implementation during migration.
"""

from __future__ import annotations

from argparse import Namespace
from typing import List


def run_setup(args: Namespace) -> int:
    """Run APRS setup via the legacy CLI, mapping known flags."""
    # Lazy import avoids pulling heavy deps at module import time
    from neo_rx.cli import main as legacy_main  # type: ignore[import]

    argv: List[str] = ["setup"]

    config = getattr(args, "config", None)
    if config:
        argv += ["--config", str(config)]

    if getattr(args, "reset", False):
        argv.append("--reset")
    if getattr(args, "dry_run", False):
        argv.append("--dry-run")
    if getattr(args, "non_interactive", False):
        argv.append("--non-interactive")

    return legacy_main(argv)
