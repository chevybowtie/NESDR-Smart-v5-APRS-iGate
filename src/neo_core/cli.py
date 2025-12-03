import argparse
import logging
import os
import sys
import time
from typing import List

# Temporary imports to delegate to existing implementation during refactor
from neo_rx.cli import main as legacy_main


def _add_common_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--device-id", help="Select SDR device by serial or index")
    p.add_argument("--instance-id", help="Instance name for concurrent runs")
    p.add_argument("--config", help="Path to mode config file")
    p.add_argument("--data-dir", help="Override base data directory")
    p.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        help="Logging level",
    )
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    p.add_argument(
        "--json", action="store_true", help="Enable JSON output for diagnostics"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neo-rx", description="Unified CLI for APRS, WSPR, and ADS-B tools"
    )
    try:
        from neo_rx import __version__
    except ImportError:
        __version__ = "0.2.3"
    parser.add_argument("--version", action="version", version=f"neo-rx {__version__}")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # APRS subcommands
    aprs = subparsers.add_parser("aprs", help="APRS mode commands")
    aprs_sub = aprs.add_subparsers(dest="verb", required=True)

    aprs_setup = aprs_sub.add_parser("setup", help="Run APRS setup wizard")
    _add_common_flags(aprs_setup)
    aprs_setup.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing configuration before starting",
    )
    aprs_setup.add_argument(
        "--non-interactive",
        action="store_true",
        help="Load answers from a config file instead of prompting",
    )
    aprs_setup.add_argument(
        "--dry-run",
        action="store_true",
        help="Run validation without writing any files",
    )

    aprs_listen = aprs_sub.add_parser("listen", help="Run APRS iGate (KISS → APRS-IS)")
    _add_common_flags(aprs_listen)
    aprs_listen.add_argument(
        "--kiss-host", help="Direwolf/KISS host", default="127.0.0.1"
    )
    aprs_listen.add_argument(
        "--kiss-port", type=int, help="Direwolf/KISS TCP port", default=8001
    )
    aprs_listen.add_argument(
        "--once", action="store_true", help="Process a single frame and exit"
    )

    aprs_diag = aprs_sub.add_parser("diagnostics", help="Run APRS diagnostics")
    _add_common_flags(aprs_diag)
    aprs_diag.add_argument(
        "--kiss-host", help="Direwolf/KISS host", default="127.0.0.1"
    )
    aprs_diag.add_argument(
        "--kiss-port", type=int, help="Direwolf/KISS TCP port", default=8001
    )
    aprs_diag.add_argument(
        "--verbose", action="store_true", help="Show extended diagnostic information"
    )

    # WSPR subcommands
    wspr = subparsers.add_parser("wspr", help="WSPR mode commands")
    wspr_sub = wspr.add_subparsers(dest="verb", required=True)

    wspr_setup = wspr_sub.add_parser("setup", help="Run WSPR setup wizard")
    _add_common_flags(wspr_setup)

    wspr_listen = wspr_sub.add_parser(
        "listen", help="Run WSPR capture → decode → upload loop"
    )
    _add_common_flags(wspr_listen)
    wspr_listen.add_argument("--band", help="Override first band (MHz)")
    wspr_listen.add_argument(
        "--duration", type=int, help="Optional run duration (seconds)"
    )

    wspr_scan = wspr_sub.add_parser("scan", help="Run multi-band scan schedule")
    _add_common_flags(wspr_scan)
    wspr_scan.add_argument("--schedule", help="Path to scan schedule file")

    wspr_cal = wspr_sub.add_parser("calibrate", help="Run PPM calibration")
    _add_common_flags(wspr_cal)
    wspr_cal.add_argument("--samples", help="Path to IQ samples for calibration")

    wspr_up = wspr_sub.add_parser(
        "upload", help="Upload decoded spots from a directory"
    )
    _add_common_flags(wspr_up)
    wspr_up.add_argument("--input", help="Directory containing decoded spots")

    wspr_diag = wspr_sub.add_parser("diagnostics", help="Run WSPR diagnostics")
    _add_common_flags(wspr_diag)
    wspr_diag.add_argument("--band", help="Band to validate (MHz)")

    # ADS-B subcommands
    adsb = subparsers.add_parser("adsb", help="ADS-B mode commands")
    adsb_sub = adsb.add_subparsers(dest="verb", required=True)

    adsb_setup = adsb_sub.add_parser("setup", help="Run ADS-B setup wizard")
    _add_common_flags(adsb_setup)
    adsb_setup.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing configuration before starting",
    )
    adsb_setup.add_argument(
        "--non-interactive",
        action="store_true",
        help="Load answers from a config file instead of prompting",
    )

    adsb_listen = adsb_sub.add_parser(
        "listen", help="Monitor ADS-B traffic via dump1090/readsb"
    )
    _add_common_flags(adsb_listen)
    adsb_listen.add_argument(
        "--json-path",
        help="Path to dump1090 aircraft.json",
        default="/run/dump1090-fa/aircraft.json",
    )
    adsb_listen.add_argument(
        "--poll-interval",
        type=float,
        help="Poll interval in seconds",
        default=1.0,
    )
    adsb_listen.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress aircraft display output",
    )

    adsb_diag = adsb_sub.add_parser("diagnostics", help="Run ADS-B diagnostics")
    _add_common_flags(adsb_diag)
    adsb_diag.add_argument(
        "--json-path",
        help="Path to dump1090 aircraft.json",
    )
    adsb_diag.add_argument(
        "--no-adsbexchange",
        action="store_true",
        help="Skip ADS-B Exchange checks",
    )
    adsb_diag.add_argument(
        "--verbose", action="store_true", help="Show extended diagnostic information"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging (stdout + file) similarly to legacy CLI
    def _resolve_log_level(candidate: str | None) -> int:
        aliases = {
            "critical": logging.CRITICAL,
            "error": logging.ERROR,
            "warning": logging.WARNING,
            "info": logging.INFO,
            "debug": logging.DEBUG,
        }
        for value in (candidate, os.getenv("NEO_RX_LOG_LEVEL")):
            if not value:
                continue
            stripped = value.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if lower in aliases:
                return aliases[lower]
            if stripped.isdigit():
                return int(stripped)
        return logging.INFO

    def _configure_logging(level_name: str | None, mode: str | None) -> None:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        handlers: list[logging.Handler] = [stream_handler]

        try:
            # Create mode-specific logs directory (aprs/wspr/adsb)
            base = os.getenv("NEO_RX_DATA_DIR")
            if base:
                from pathlib import Path

                base_path = Path(base)
            else:
                # Fallback to legacy location via neo_rx.config
                from neo_rx import config as config_module

                base_path = config_module.get_data_dir()
            subdir = (mode or "aprs").strip().lower()
            if subdir not in {"aprs", "wspr", "adsb"}:
                subdir = "aprs"
            log_dir = base_path / "logs" / subdir
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "neo-rx.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_formatter = logging.Formatter(
                "%(asctime)sZ %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
            )
            file_formatter.converter = time.gmtime
            file_handler.setFormatter(file_formatter)
            handlers.append(file_handler)
        except Exception:
            pass

        logging.basicConfig(level=_resolve_log_level(level_name), handlers=handlers, force=True)

    # Propagate instance/data directory overrides via environment so that
    # downstream modules use the same namespacing without signature changes.
    if getattr(args, "instance_id", None):
        os.environ.setdefault("NEO_RX_INSTANCE_ID", str(args.instance_id))
    if getattr(args, "data_dir", None):
        os.environ.setdefault("NEO_RX_DATA_DIR", str(args.data_dir))

    # Ensure logging is configured before delegating to subcommands
    _configure_logging(getattr(args, "log_level", None), getattr(args, "mode", None))

    # Delegate to existing neo_rx CLI until mode-specific refactor completes
    if args.mode == "aprs":
        if args.verb == "listen":
            from neo_aprs.commands.listen import run_listen as aprs_run_listen  # type: ignore[import]

            return aprs_run_listen(args)
        elif args.verb == "setup":
            from neo_aprs.commands.setup import run_setup as aprs_run_setup  # type: ignore[import]

            return aprs_run_setup(args)
        elif args.verb == "diagnostics":
            from neo_aprs.commands.diagnostics import (  # type: ignore[import]
                run_diagnostics as aprs_run_diagnostics,
            )

            return aprs_run_diagnostics(args)
        else:
            parser.error("Unknown APRS verb")
    elif args.mode == "wspr":
        if args.verb == "setup":
            # No dedicated legacy setup; keep existing diagnostics mapping
            argv2: List[str] = ["wspr", "--diagnostics"]
            if getattr(args, "json", False):
                argv2.append("--json")
            return legacy_main(argv2)
        elif args.verb == "listen":
            from neo_wspr.commands.listen import run_listen  # type: ignore[import]

            return run_listen(args)
        elif args.verb == "scan":
            from neo_wspr.commands.scan import run_scan  # type: ignore[import]

            return run_scan(args)
        elif args.verb == "calibrate":
            from neo_wspr.commands.calibrate import run_calibrate  # type: ignore[import]

            return run_calibrate(args)
        elif args.verb == "upload":
            from neo_wspr.commands.upload import run_upload  # type: ignore[import]

            return run_upload(args)
        elif args.verb == "diagnostics":
            from neo_wspr.commands.diagnostics import run_diagnostics  # type: ignore[import]

            return run_diagnostics(args)
        else:
            parser.error("Unknown WSPR verb")
    elif args.mode == "adsb":
        if args.verb == "listen":
            from neo_adsb.commands.listen import run_listen as adsb_run_listen  # type: ignore[import]

            return adsb_run_listen(args)
        elif args.verb == "setup":
            from neo_adsb.commands.setup import run_setup as adsb_run_setup  # type: ignore[import]

            return adsb_run_setup(args)
        elif args.verb == "diagnostics":
            from neo_adsb.commands.diagnostics import (  # type: ignore[import]
                run_diagnostics_cmd as adsb_run_diagnostics,
            )

            return adsb_run_diagnostics(args)
        else:
            parser.error("Unknown ADS-B verb")
    else:
        parser.error("Unknown mode")

    return 0


if __name__ == "__main__":
    sys.exit(main())
