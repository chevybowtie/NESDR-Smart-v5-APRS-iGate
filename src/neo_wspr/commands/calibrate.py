"""WSPR calibrate command wrapper.

Delegates to legacy neo_rx wspr --calibrate.
"""

from __future__ import annotations

from argparse import Namespace
from typing import List


def run_calibrate(args: Namespace) -> int:
    from neo_rx.cli import main as legacy_main  # type: ignore[import]

    argv: List[str] = ["wspr", "--calibrate"]
    band = getattr(args, "band", None)
    if band:
        argv += ["--band", str(band)]
    # samples has no legacy mapping; intentionally ignored
    return legacy_main(argv)
