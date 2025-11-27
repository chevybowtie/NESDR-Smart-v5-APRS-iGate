"""WSPR upload command wrapper.

Delegates to legacy neo_rx wspr --upload and forwards spots directory.
"""

from __future__ import annotations

from argparse import Namespace
from typing import List


def run_upload(args: Namespace) -> int:
    from neo_rx.cli import main as legacy_main  # type: ignore[import]

    argv: List[str] = ["wspr", "--upload"]
    input_dir = getattr(args, "input", None)
    if input_dir:
        argv += ["--spots-file", str(input_dir)]
    # heartbeat flag is not exposed in unified CLI; not forwarded
    return legacy_main(argv)
