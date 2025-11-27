"""WSPR scan command wrapper.

Delegates to legacy neo_rx wspr --scan.
"""

from __future__ import annotations

from argparse import Namespace
from typing import List


def run_scan(args: Namespace) -> int:
    from neo_rx.cli import main as legacy_main  # type: ignore[import]

    argv: List[str] = ["wspr", "--scan"]
    # schedule has no legacy mapping; intentionally ignored
    if getattr(args, "json", False):  # if unified CLI adds json later
        argv.append("--json")
    return legacy_main(argv)
