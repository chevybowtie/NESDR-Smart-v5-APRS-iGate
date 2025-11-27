"""WSPR diagnostics command wrapper.

Delegates to legacy neo_rx wspr --diagnostics.
"""

from __future__ import annotations

from argparse import Namespace
from typing import List


def run_diagnostics(args: Namespace) -> int:
    from neo_rx.cli import main as legacy_main  # type: ignore[import]

    argv: List[str] = ["wspr", "--diagnostics"]
    if getattr(args, "json", False):
        argv.append("--json")
    band = getattr(args, "band", None)
    if band:
        argv += ["--band", str(band)]
    return legacy_main(argv)
