"""Command-line interface entry points for the NESDR APRS iGate."""

from __future__ import annotations

import argparse
import sys
from argparse import Namespace
from typing import Protocol

from nesdr_igate.commands import (  # type: ignore[import]
    run_diagnostics,
    run_listen,
    run_setup,
)

DEFAULT_COMMAND = "listen"


class CommandHandler(Protocol):
    """Callable signature for CLI subcommands."""

    def __call__(self, args: Namespace) -> int:  # pragma: no cover - typing hook
        ...


def build_parser(handlers: dict[str, CommandHandler] | None = None) -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""

    handlers = handlers or _command_handlers()

    parser = argparse.ArgumentParser(
        prog="nesdr-igate",
        description="NESDR Smart v5 APRS iGate utility (work in progress)",
    )
    parser.set_defaults(command=DEFAULT_COMMAND, handler=handlers[DEFAULT_COMMAND])

    subparsers = parser.add_subparsers(dest="command", required=False)

    listen_parser = subparsers.add_parser(
        "listen", help="Run the SDR capture and APRS iGate pipeline"
    )
    listen_parser.set_defaults(command="listen", handler=handlers["listen"])
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
    setup_parser.set_defaults(command="setup", handler=handlers["setup"])
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
    diagnostics_parser.set_defaults(command="diagnostics", handler=handlers["diagnostics"])
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

    handlers = _command_handlers()
    parser = build_parser(handlers)

    argv_list = list(sys.argv[1:] if argv is None else argv)
    normalized = _normalize_argv(argv_list, handlers)
    args = parser.parse_args(normalized)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    return handler(args)


def _command_handlers() -> dict[str, CommandHandler]:
    """Return the mapping of subcommand names to handler callables."""

    return {
        "listen": run_listen,
        "setup": run_setup,
        "diagnostics": run_diagnostics,
    }


def _normalize_argv(argv: list[str], handlers: dict[str, CommandHandler]) -> list[str]:
    """Inject a default subcommand when the user omits one."""

    if not argv:
        return [DEFAULT_COMMAND]

    first = argv[0]
    if first in ("-h", "--help"):
        return argv

    known_commands = set(handlers.keys())

    if first.startswith("-"):
        return [DEFAULT_COMMAND, *argv]

    if first in known_commands:
        return argv

    return argv


if __name__ == "__main__":  # pragma: no cover - direct CLI execution path
    raise SystemExit(main())
