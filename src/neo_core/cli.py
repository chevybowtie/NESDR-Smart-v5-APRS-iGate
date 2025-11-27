import argparse
import sys
from typing import List

# Temporary imports to delegate to existing implementation during refactor
from neo_rx.cli import main as legacy_main


def _add_common_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--device-id", help="Select SDR device by serial or index")
    p.add_argument("--instance-id", help="Instance name for concurrent runs")
    p.add_argument("--config", help="Path to mode config file")
    p.add_argument("--data-dir", help="Override base data directory")
    p.add_argument("--log-level", choices=["debug", "info", "warning", "error"], help="Logging level")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    p.add_argument("--json", action="store_true", help="Enable JSON output for diagnostics")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neo-rx", description="Unified CLI for APRS and WSPR tools")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # APRS subcommands
    aprs = subparsers.add_parser("aprs", help="APRS mode commands")
    aprs_sub = aprs.add_subparsers(dest="verb", required=True)

    aprs_setup = aprs_sub.add_parser("setup", help="Run APRS setup wizard")
    _add_common_flags(aprs_setup)
    aprs_setup.add_argument(
        "--reset", action="store_true", help="Delete existing configuration before starting"
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
    aprs_listen.add_argument("--kiss-host", help="Direwolf/KISS host", default="127.0.0.1")
    aprs_listen.add_argument("--kiss-port", type=int, help="Direwolf/KISS TCP port", default=8001)

    aprs_diag = aprs_sub.add_parser("diagnostics", help="Run APRS diagnostics")
    _add_common_flags(aprs_diag)
    aprs_diag.add_argument("--kiss-host", help="Direwolf/KISS host", default="127.0.0.1")
    aprs_diag.add_argument("--kiss-port", type=int, help="Direwolf/KISS TCP port", default=8001)
    aprs_diag.add_argument("--verbose", action="store_true", help="Show extended diagnostic information")

    # WSPR subcommands
    wspr = subparsers.add_parser("wspr", help="WSPR mode commands")
    wspr_sub = wspr.add_subparsers(dest="verb", required=True)

    wspr_setup = wspr_sub.add_parser("setup", help="Run WSPR setup wizard")
    _add_common_flags(wspr_setup)

    wspr_worker = wspr_sub.add_parser("worker", help="Run WSPR capture → decode → upload loop")
    _add_common_flags(wspr_worker)
    wspr_worker.add_argument("--band", help="Override first band (MHz)")
    wspr_worker.add_argument("--duration", type=int, help="Optional run duration (seconds)")

    wspr_scan = wspr_sub.add_parser("scan", help="Run multi-band scan schedule")
    _add_common_flags(wspr_scan)
    wspr_scan.add_argument("--schedule", help="Path to scan schedule file")

    wspr_cal = wspr_sub.add_parser("calibrate", help="Run PPM calibration")
    _add_common_flags(wspr_cal)
    wspr_cal.add_argument("--samples", help="Path to IQ samples for calibration")

    wspr_up = wspr_sub.add_parser("upload", help="Upload decoded spots from a directory")
    _add_common_flags(wspr_up)
    wspr_up.add_argument("--input", help="Directory containing decoded spots")

    wspr_diag = wspr_sub.add_parser("diagnostics", help="Run WSPR diagnostics")
    _add_common_flags(wspr_diag)
    wspr_diag.add_argument("--band", help="Band to validate (MHz)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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
        argv2: List[str] = ["wspr"]
        if args.verb == "setup":
            # Legacy CLI does not have a dedicated wspr setup; run diagnostics for now
            if getattr(args, "json", False):
                argv2.append("--json")
            argv2.append("--diagnostics")
        elif args.verb == "worker":
            argv2.append("--start")
            if args.band:
                argv2 += ["--band", args.band]
            if args.duration:
                # no direct mapping in legacy CLI; ignore
                pass
        elif args.verb == "scan":
            argv2.append("--scan")
        elif args.verb == "calibrate":
            argv2.append("--calibrate")
        elif args.verb == "upload":
            argv2.append("--upload")
            if args.input:
                argv2 += ["--spots-file", args.input]
        elif args.verb == "diagnostics":
            argv2.append("--diagnostics")
            if getattr(args, "json", False):
                argv2.append("--json")
            if args.band:
                argv2 += ["--band", args.band]
        else:
            parser.error("Unknown WSPR verb")
        return legacy_main(argv2)
    else:
        parser.error("Unknown mode")

    return 0


if __name__ == "__main__":
    sys.exit(main())
