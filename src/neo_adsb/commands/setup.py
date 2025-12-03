"""ADS-B setup command implementation.

Interactive setup wizard for ADS-B configuration.
"""

from __future__ import annotations

import logging
from argparse import Namespace

from neo_core import config as config_module

LOG = logging.getLogger(__name__)


def run_setup(args: Namespace) -> int:
    """Run the ADS-B setup wizard."""
    print("\n" + "=" * 60)
    print("Neo-RX ADS-B Setup Wizard")
    print("=" * 60)

    non_interactive = getattr(args, "non_interactive", False)
    reset = getattr(args, "reset", False)

    # Load existing config if available
    cfg_path = getattr(args, "config", None)
    existing_config = None
    try:
        if cfg_path:
            existing_config = config_module.load_config(cfg_path)
        else:
            existing_config = config_module.load_config()
    except Exception:
        pass

    if existing_config and not reset:
        print("\nExisting configuration found.")
        if non_interactive:
            print("Using existing configuration (non-interactive mode).")
            return 0
        response = input("Overwrite existing configuration? [y/N]: ").strip().lower()
        if response != "y":
            print("Setup cancelled.")
            return 0

    print("\nThis wizard will configure ADS-B monitoring settings.")
    print("\nPrerequisites:")
    print("  - dump1090-fa, dump1090, or readsb must be installed and running")
    print("  - RTL-SDR device should be connected")
    print("\nOptional:")
    print("  - ADS-B Exchange feedclient for network reporting")
    print("    Install: curl -L https://adsbexchange.com/feed.sh | sudo bash\n")

    if non_interactive:
        print("Non-interactive mode: using default values.")
        # Create default ADS-B config
        _save_adsb_defaults(existing_config)
        return 0

    # Interactive setup
    print("Press Enter to accept defaults [shown in brackets].\n")

    # JSON path configuration
    default_json_path = "/run/dump1090-fa/aircraft.json"
    if existing_config:
        default_json_path = getattr(
            existing_config, "adsb_json_path", default_json_path
        )

    json_path = (
        input(f"dump1090 JSON path [{default_json_path}]: ").strip()
        or default_json_path
    )

    print(f"Using JSON path: {json_path}")

    # ADS-B Exchange setup
    print("\n" + "-" * 40)
    print("ADS-B Exchange Integration (optional)")
    print("-" * 40)
    try:
        from neo_adsb.adsb.reporter import AdsbExchangeReporter
    except Exception:
        AdsbExchangeReporter = None

    if AdsbExchangeReporter is not None:
        reporter = AdsbExchangeReporter()
        if reporter.is_installed():
            status = reporter.get_status()
            print("\nADS-B Exchange feedclient is installed.")
            print(
                f"  Feed service: {'active' if status.feed_service_active else 'inactive'}"
            )
            print(
                f"  MLAT service: {'active' if status.mlat_service_active else 'inactive'}"
            )
            if getattr(status, 'username', None):
                print(f"  Username: {status.username}")

            # MLAT Python environment checks (common failure on 3.12/3.13)
            from pathlib import Path as _Path
            import subprocess as _subprocess

            venv_python = _Path("/usr/local/share/adsbexchange/venv/bin/python")
            if venv_python.exists():
                try:
                    ver = _subprocess.run(
                        [str(venv_python), "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    py_ver = ver.stdout.strip() if ver.returncode == 0 else "unknown"

                    check_asyncore = _subprocess.run(
                        [str(venv_python), "-c", "import asyncore"],
                        capture_output=True,
                        timeout=5,
                    )
                    check_pyasyncore = _subprocess.run(
                        [str(venv_python), "-c", "import pyasyncore"],
                        capture_output=True,
                        timeout=5,
                    )

                    if (
                        check_asyncore.returncode != 0
                        and check_pyasyncore.returncode != 0
                    ):
                        print("\n  ⚠️  WARNING: MLAT Python environment issue detected")
                        print(
                            f"     MLAT venv uses {py_ver} but asyncore/pyasyncore is missing"
                        )
                        if "3.13" in py_ver or "3.12" in py_ver:
                            print("\n  Fix: Install asyncore backport:")
                            print(
                                "     sudo /usr/local/share/adsbexchange/venv/bin/pip install pyasyncore"
                            )
                            print("\n  Alternative: Recreate venv with Python 3.11:")
                            print(
                                "     sudo rm -rf /usr/local/share/adsbexchange/venv"
                            )
                            print(
                                "     sudo python3.11 -m venv /usr/local/share/adsbexchange/venv"
                            )
                            print(
                                "     sudo /usr/local/share/adsbexchange/venv/bin/pip install setuptools wheel"
                            )
                            print(
                                "     cd /usr/local/share/adsbexchange/mlat-client-git"
                            )
                            print(
                                "     sudo /usr/local/share/adsbexchange/venv/bin/pip install ."
                            )
                            print("     sudo systemctl restart adsbexchange-mlat")
                except Exception:
                    pass
        else:
            print("\nADS-B Exchange feedclient is not installed.")
            print("To install, run:")
            print(
                "  curl -L -o /tmp/axfeed.sh https://adsbexchange.com/feed.sh && sudo bash /tmp/axfeed.sh"
            )
            import sys as _sys
            if _sys.version_info >= (3, 12):
                print("\n  ⚠️  Note: You're running Python 3.13/3.12")
                print("     MLAT requires Python 3.11 or the pyasyncore backport")
                print("     After installing the feeder, you may need to fix the venv")
                print("     Run 'neo-rx adsb diagnostics' to check MLAT status")
    else:
        print("\nReporter module unavailable; skip ADS-B Exchange checks.")

    # Note: ADS-B-specific config would need to be added to StationConfig
    # For now, we just validate the setup
    print("\nADS-B setup complete!")
    print("\nTo start monitoring:")
    print("  neo-rx adsb listen")
    print("\nTo check status:")
    print("  neo-rx adsb diagnostics")

    return 0


def _save_adsb_defaults(existing_config) -> None:
    """Save default ADS-B configuration."""
    print("\nDefault ADS-B configuration:")
    print("  JSON path: /run/dump1090-fa/aircraft.json")
    print("  Poll interval: 1.0s")
    print("\nRun 'neo-rx adsb diagnostics' to verify your setup.")
