"""Command-line interface entry points for the Neo-RX."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from argparse import Namespace
from typing import Callable, Dict

from neo_rx import __version__
from neo_rx import config as config_module

from neo_rx.commands import (  # type: ignore[import]
    run_diagnostics,
    run_listen,
    run_setup,
)

CommandHandler = Callable[[Namespace], int]

_LOG_LEVEL_ALIASES: dict[str, int] = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}


def _package_version() -> str:
    # Use the package-level canonical version value. This avoids
    # repeated importlib.metadata lookups and keeps a single source of
    # truth for runtime reporting (see ``neo_rx.__version__``).
    return __version__


def _resolve_log_level(candidate: str | None) -> int:
    for value in (candidate, os.getenv("NEO_RX_LOG_LEVEL")):
        if not value:
            continue
        stripped = value.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower in _LOG_LEVEL_ALIASES:
            return _LOG_LEVEL_ALIASES[lower]
        if stripped.isdigit():
            return int(stripped)
    return logging.INFO


def _configure_logging(level_name: str | None) -> None:
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    handlers: list[logging.Handler] = [stream_handler]

    try:
        # Legacy CLI primarily serves APRS flow; build logs path relative to
        # get_data_dir so monkeypatching in tests affects behavior.
        base = config_module.get_data_dir()
        log_dir = base / "logs" / "aprs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "neo-rx.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_formatter = logging.Formatter(
            "%(asctime)sZ %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        )
        file_formatter.converter = time.gmtime
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)
    except OSError:
        # If we can't create the log directory or file, continue without file logging.
        pass

    logging.basicConfig(
        level=_resolve_log_level(level_name),
        handlers=handlers,
        force=True,
    )


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="neo-rx",
        description="Neo-RX utility.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment overrides:\n"
            "  NEO_RX_LOG_LEVEL    Default logging level when --log-level is omitted.\n"
            "  NEO_RX_CONFIG_PATH  Path to config.toml used by setup/listen/diagnostics."
        ),
    )
    parser.add_argument(
        "--log-level",
        help="Set log verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL or numeric)",
    )
    parser.add_argument(
        "--color",
        dest="color",
        action="store_true",
        help="Force-enable colorized output (overrides auto-detection)",
    )
    parser.add_argument(
        "--no-color",
        dest="no_color",
        action="store_true",
        help="Disable colorized output",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show package version and exit",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)
    subparser_map: Dict[str, argparse.ArgumentParser] = {}

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
    subparser_map["listen"] = listen_parser

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
    subparser_map["setup"] = setup_parser

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
    subparser_map["diagnostics"] = diagnostics_parser

    setattr(parser, "_nesdr_subparser_map", subparser_map)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Process CLI arguments and dispatch to the requested command."""
    parser = build_parser()
    subparser_map: Dict[str, argparse.ArgumentParser] = getattr(
        parser, "_nesdr_subparser_map", {}
    )
    args, remainder = parser.parse_known_args(argv)

    if getattr(args, "version", False):
        print(f"{parser.prog} {_package_version()}")
        return 0

    _configure_logging(getattr(args, "log_level", None))

    handlers: dict[str, CommandHandler] = {
        "listen": run_listen,
        "setup": run_setup,
        "diagnostics": run_diagnostics,
    }

    if args.command is None:
        listen_parser = subparser_map.get("listen")
        if listen_parser is None:
            parser.print_help()
            return 0
        listen_namespace = listen_parser.parse_args(remainder)
        setattr(listen_namespace, "command", "listen")
        return handlers["listen"](listen_namespace)

    if remainder:
        parser.error(f"Unknown arguments: {' '.join(remainder)}")

    handler = handlers.get(args.command)
    if handler is None:  # pragma: no cover - future safeguard
        parser.error(f"Unknown command: {args.command}")

    return handler(args)


if __name__ == "__main__":  # pragma: no cover - direct CLI execution path
    raise SystemExit(main())
