"""POCSAG setup command."""

from __future__ import annotations

import logging
from argparse import Namespace
from pathlib import Path

from neo_core import config as config_module

LOG = logging.getLogger(__name__)


def run_setup(args: Namespace) -> int:
    """Run POCSAG setup wizard."""
    config_path = config_module.resolve_config_path(getattr(args, "config", None))
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    try:
        station_config = config_module.load_config(config_path)
    except FileNotFoundError:
        station_config = {}
    except ValueError as exc:
        LOG.error("Config invalid: %s", exc)
        return 1

    print("POCSAG Setup")
    print("============")
    print()

    # Frequency
    current_freq = getattr(station_config, "pocsag_frequency_hz", 152840000)
    print(f"Current POCSAG frequency: {current_freq} Hz ({current_freq / 1e6:.3f} MHz)")
    print("Common US pager frequencies:")
    print("  152.840 MHz - Common nationwide")
    print("  158.100 MHz - Some regional systems")
    print("  158.760 MHz - Hospital/EMS pagers")
    try:
        freq_input = input(f"Enter frequency in Hz (default {current_freq}): ").strip()
        if freq_input:
            setattr(station_config, "pocsag_frequency_hz", int(freq_input))
    except ValueError:
        print("Invalid frequency, keeping current value.")

    # Save config
    try:
        config_module.save_config(station_config, config_path)
        print(f"\nConfiguration saved to {config_path}")
    except Exception as exc:
        LOG.error("Failed to save config: %s", exc)
        return 1

    print("\nPOCSAG setup complete!")
    print("Run 'neo-rx pocsag listen' to start monitoring.")
    return 0