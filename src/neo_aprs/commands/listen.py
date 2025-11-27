"""APRS listen command wrapper.

During migration, this delegates to the legacy neo_rx CLI implementation.
Once all neo_core.radio dependencies are fully migrated, this can be replaced
with the real implementation.
"""

from __future__ import annotations

from argparse import Namespace
from typing import List


def run_listen(args: Namespace) -> int:
    """Run APRS listen via the legacy CLI, mapping known flags."""
    # Import lazily to avoid pulling heavy dependencies at module import time
    from neo_rx.cli import main as legacy_main  # type: ignore[import]
    argv: List[str] = ["listen"]

    config = getattr(args, "config", None)
    if config:
        argv += ["--config", str(config)]

    if getattr(args, "once", False):
        argv.append("--once")

    if getattr(args, "no_aprsis", False):
        argv.append("--no-aprsis")

    return legacy_main(argv)
