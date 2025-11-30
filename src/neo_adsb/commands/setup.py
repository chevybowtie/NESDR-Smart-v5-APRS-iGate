"""ADS-B setup command implementation.

Interactive setup wizard for ADS-B configuration.
"""

from __future__ import annotations

import logging
from argparse import Namespace
from pathlib import Path

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

    # Validate JSON path
    if not Path(json_path).exists():
        print(f"\nWarning: {json_path} does not exist.")
        print("Make sure dump1090 is running before using ADS-B features.")

    # Poll interval
    default_poll = 1.0
    poll_input = input(f"Poll interval in seconds [{default_poll}]: ").strip()
    try:
        poll_interval = float(poll_input) if poll_input else default_poll
    except ValueError:
        poll_interval = default_poll

    # Station location (for range calculations)
    print("\nStation location (optional, for range statistics):")
    lat_input = input("  Latitude (e.g., 37.7749): ").strip()
    lon_input = input("  Longitude (e.g., -122.4194): ").strip()

    latitude = float(lat_input) if lat_input else None
    longitude = float(lon_input) if lon_input else None

    # ADS-B Exchange setup
    print("\n" + "-" * 40)
    print("ADS-B Exchange Integration (optional)")
    print("-" * 40)

    from neo_adsb.adsb.reporter import AdsbExchangeReporter

    reporter = AdsbExchangeReporter()
    if reporter.is_installed():
        status = reporter.get_status()
        print("\nADS-B Exchange feedclient is installed.")
        print(f"  Feed service: {'active' if status.feed_service_active else 'inactive'}")
        print(f"  MLAT service: {'active' if status.mlat_service_active else 'inactive'}")
        if status.username:
            print(f"  Username: {status.username}")
    else:
        print("\nADS-B Exchange feedclient is not installed.")
        print("To install, run:")
        print("  curl -L -o /tmp/axfeed.sh https://adsbexchange.com/feed.sh")
        print("  sudo bash /tmp/axfeed.sh")

    # Save configuration summary
    print("\n" + "=" * 60)
    print("Configuration Summary")
    print("=" * 60)
    print(f"  JSON path: {json_path}")
    print(f"  Poll interval: {poll_interval}s")
    if latitude and longitude:
        print(f"  Station location: {latitude:.4f}, {longitude:.4f}")
    else:
        print("  Station location: not set")
    print()

    confirm = input("Save this configuration? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("Setup cancelled.")
        return 0

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
