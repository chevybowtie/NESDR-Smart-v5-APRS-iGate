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

# Import subpackage commands for namespaced CLI
try:
    from neo_aprs.commands import (
        run_listen as aprs_listen,
        run_setup as aprs_setup,
        run_diagnostics as aprs_diagnostics,
    )
except ImportError:
    aprs_listen = None  # type: ignore
    aprs_setup = None  # type: ignore
    aprs_diagnostics = None  # type: ignore

try:
    from neo_wspr.commands import (
        run_listen as wspr_listen,
        run_scan as wspr_scan,
        run_calibrate as wspr_calibrate,
        run_upload as wspr_upload,
        run_diagnostics as wspr_diagnostics,
    )
except ImportError:
    wspr_listen = None  # type: ignore
    wspr_scan = None  # type: ignore
    wspr_calibrate = None  # type: ignore
    wspr_upload = None  # type: ignore
    wspr_diagnostics = None  # type: ignore

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
        action="version",
        version=f"neo-rx {_package_version()}",
        help="Show package version and exit",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)
    subparser_map: Dict[str, argparse.ArgumentParser] = {}

    # Legacy top-level commands (for backward compatibility)
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

    # APRS namespaced commands
    if aprs_listen is not None:
        aprs_parser = subparsers.add_parser("aprs", help="APRS iGate commands")
        aprs_subparsers = aprs_parser.add_subparsers(dest="aprs_command", required=True)

        aprs_listen_parser = aprs_subparsers.add_parser(
            "listen", help="Run the SDR capture and APRS iGate pipeline"
        )
        aprs_listen_parser.add_argument(
            "--config",
            help="Path to configuration file (overrides default location)",
        )
        aprs_listen_parser.add_argument(
            "--once",
            action="store_true",
            help="Process a single batch of samples and exit (debug/testing)",
        )
        aprs_listen_parser.add_argument(
            "--no-aprsis",
            action="store_true",
            help="Disable APRS-IS uplink (receive-only mode)",
        )
        aprs_listen_parser.add_argument(
            "--instance-id",
            help="Instance identifier for isolated data/log directories",
        )
        aprs_listen_parser.add_argument(
            "--device-id",
            help="RTL-SDR device serial number or index",
        )
        subparser_map["aprs:listen"] = aprs_listen_parser

        aprs_setup_parser = aprs_subparsers.add_parser(
            "setup", help="Run the APRS onboarding wizard"
        )
        aprs_setup_parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing configuration before starting",
        )
        aprs_setup_parser.add_argument(
            "--non-interactive",
            action="store_true",
            help="Load answers from a config file instead of prompting",
        )
        aprs_setup_parser.add_argument(
            "--config",
            help="Path to onboarding configuration template",
        )
        aprs_setup_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run validation without writing any files",
        )
        subparser_map["aprs:setup"] = aprs_setup_parser

        aprs_diagnostics_parser = aprs_subparsers.add_parser(
            "diagnostics", help="Display APRS system and radio health checks"
        )
        aprs_diagnostics_parser.add_argument(
            "--config",
            help="Path to configuration file (overrides default location)",
        )
        aprs_diagnostics_parser.add_argument(
            "--json",
            action="store_true",
            help="Emit diagnostics in JSON format",
        )
        aprs_diagnostics_parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show extended diagnostic information",
        )
        subparser_map["aprs:diagnostics"] = aprs_diagnostics_parser

    # WSPR namespaced commands
    if wspr_listen is not None:
        wspr_parser = subparsers.add_parser("wspr", help="WSPR monitoring commands")
        wspr_subparsers = wspr_parser.add_subparsers(dest="wspr_command", required=True)

        wspr_listen_parser = wspr_subparsers.add_parser(
            "listen", help="Run WSPR monitoring listener"
        )
        wspr_listen_parser.add_argument(
            "--config",
            help="Path to configuration file (overrides default location)",
        )
        wspr_listen_parser.add_argument(
            "--band",
            help="Monitor a single band (80m, 40m, 30m, 20m, 10m, 6m, 2m, 70cm)",
        )
        wspr_listen_parser.add_argument(
            "--instance-id",
            help="Instance identifier for isolated data/log directories",
        )
        wspr_listen_parser.add_argument(
            "--device-id",
            help="RTL-SDR device serial number or index",
        )
        subparser_map["wspr:listen"] = wspr_listen_parser

        wspr_scan_parser = wspr_subparsers.add_parser(
            "scan", help="Multi-band WSPR scan"
        )
        wspr_scan_parser.add_argument(
            "--config",
            help="Path to configuration file (overrides default location)",
        )
        wspr_scan_parser.add_argument(
            "--instance-id",
            help="Instance identifier for isolated data/log directories",
        )
        wspr_scan_parser.add_argument(
            "--device-id",
            help="RTL-SDR device serial number or index",
        )
        subparser_map["wspr:scan"] = wspr_scan_parser

        wspr_calibrate_parser = wspr_subparsers.add_parser(
            "calibrate", help="Calibrate frequency correction"
        )
        wspr_calibrate_parser.add_argument(
            "--config",
            help="Path to configuration file (overrides default location)",
        )
        wspr_calibrate_parser.add_argument(
            "--samples",
            help="Path to IQ sample file for calibration",
        )
        wspr_calibrate_parser.add_argument(
            "--device-id",
            help="RTL-SDR device serial number or index",
        )
        subparser_map["wspr:calibrate"] = wspr_calibrate_parser

        wspr_upload_parser = wspr_subparsers.add_parser(
            "upload", help="Upload queued WSPR spots to WSPRnet"
        )
        wspr_upload_parser.add_argument(
            "--config",
            help="Path to configuration file (overrides default location)",
        )
        wspr_upload_parser.add_argument(
            "--heartbeat",
            action="store_true",
            help="Send heartbeat ping when queue is empty",
        )
        wspr_upload_parser.add_argument(
            "--json",
            action="store_true",
            help="Output upload results in JSON format",
        )
        wspr_upload_parser.add_argument(
            "--instance-id",
            help="Instance identifier for isolated data/log directories",
        )
        subparser_map["wspr:upload"] = wspr_upload_parser

        wspr_diagnostics_parser = wspr_subparsers.add_parser(
            "diagnostics", help="Display WSPR system and radio health checks"
        )
        wspr_diagnostics_parser.add_argument(
            "--config",
            help="Path to configuration file (overrides default location)",
        )
        wspr_diagnostics_parser.add_argument(
            "--json",
            action="store_true",
            help="Emit diagnostics in JSON format",
        )
        wspr_diagnostics_parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show extended diagnostic information",
        )
        wspr_diagnostics_parser.add_argument(
            "--band",
            help="Test specific band (80m, 40m, 30m, 20m, 10m, 6m, 2m, 70cm)",
        )
        subparser_map["wspr:diagnostics"] = wspr_diagnostics_parser

    setattr(parser, "_nesdr_subparser_map", subparser_map)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Process CLI arguments and dispatch to the requested command."""
    parser = build_parser()
    args, remainder = parser.parse_known_args(argv)

    if getattr(args, "version", False):
        print(f"{parser.prog} {_package_version()}")
        return 0

    _configure_logging(getattr(args, "log_level", None))

    # Legacy top-level handlers (backward compatibility)
    handlers: dict[str, CommandHandler] = {
        "listen": run_listen,
        "setup": run_setup,
        "diagnostics": run_diagnostics,
    }

    # Namespaced APRS handlers
    aprs_handlers: dict[str, CommandHandler] = {}
    if aprs_listen is not None:
        aprs_handlers = {
            "listen": aprs_listen,
            "setup": aprs_setup,
            "diagnostics": aprs_diagnostics,
        }

    # Namespaced WSPR handlers
    wspr_handlers: dict[str, CommandHandler] = {}
    if wspr_listen is not None:
        wspr_handlers = {
            "listen": wspr_listen,
            "scan": wspr_scan,
            "calibrate": wspr_calibrate,
            "upload": wspr_upload,
            "diagnostics": wspr_diagnostics,
        }

    # Handle namespaced aprs commands
    if args.command == "aprs":
        aprs_command = getattr(args, "aprs_command", None)
        if aprs_command is None:
            parser.error("aprs: command required")
        # Detect leftover unknown arguments from initial parse
        if remainder:
            parser.error("unrecognized arguments: " + " ".join(remainder))
        handler = aprs_handlers.get(aprs_command)
        if handler is None:
            parser.error(f"aprs: unknown command: {aprs_command}")
        return handler(args)

    # Handle namespaced wspr commands
    if args.command == "wspr":
        wspr_command = getattr(args, "wspr_command", None)
        if wspr_command is None:
            parser.error("wspr: command required")
        if remainder:
            parser.error("unrecognized arguments: " + " ".join(remainder))
        handler = wspr_handlers.get(wspr_command)
        if handler is None:
            parser.error(f"wspr: unknown command: {wspr_command}")
        return handler(args)

    # Require an explicit command; no silent default behavior
    if args.command is None:
        parser.error("command required")

    if remainder:
        parser.error(f"Unknown arguments: {' '.join(remainder)}")

    # Handle legacy top-level commands
    handler = handlers.get(args.command)
    if handler is None:  # pragma: no cover - future safeguard
        parser.error(f"Unknown command: {args.command}")

    return handler(args)


if __name__ == "__main__":  # pragma: no cover - direct CLI execution path
    raise SystemExit(main())
