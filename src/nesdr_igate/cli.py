"""Command-line interface entry points for the NESDR APRS iGate."""

from __future__ import annotations

import argparse
from argparse import Namespace
from typing import Callable

from nesdr_igate.commands import (  # type: ignore[import]
    run_diagnostics,
    run_listen,
    run_setup,
)

CommandHandler = Callable[[Namespace], int]


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="nesdr-igate",
        description="NESDR Smart v5 APRS iGate utility (work in progress)",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    listen_parser = subparsers.add_parser(
        "listen", help="Run the SDR capture and APRS iGate pipeline"
    )
    listen_parser.add_argument(
        "--config",
        help="Path to configuration file (overrides default location)",
    )
    listen_parser.add_argument(
        "--once",
        action="store_true",
        help="Process a single batch of samples and exit (debug/testing)",
    )
    listen_parser.add_argument(
        "--no-aprsis",
        action="store_true",
        help="Disable APRS-IS uplink (receive-only mode)",
    )

    setup_parser = subparsers.add_parser("setup", help="Run the onboarding wizard")
    setup_parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing configuration before starting",
    )
    setup_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Load answers from a config file instead of prompting",
    )
    setup_parser.add_argument(
        "--config",
        help="Path to onboarding configuration template",
    )
    setup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run validation without writing any files",
    )

    diagnostics_parser = subparsers.add_parser(
        "diagnostics", help="Display system and radio health checks"
    )
    diagnostics_parser.add_argument(
        "--config",
        help="Path to configuration file (overrides default location)",
    )
    diagnostics_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit diagnostics in JSON format",
    )
    diagnostics_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show extended diagnostic information",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Process CLI arguments and dispatch to the requested command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    handlers: dict[str, CommandHandler] = {
        "listen": run_listen,
        "setup": run_setup,
        "diagnostics": run_diagnostics,
    }

    handler = handlers.get(args.command)
    if handler is None:  # pragma: no cover - future safeguard
        parser.error(f"Unknown command: {args.command}")

    return handler(args)


if __name__ == "__main__":  # pragma: no cover - direct CLI execution path
    raise SystemExit(main())
