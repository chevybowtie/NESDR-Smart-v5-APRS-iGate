"""Find and list RTL-SDR devices command.

Helps users discover their device serial numbers for configuration.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from argparse import Namespace

LOG = logging.getLogger(__name__)


def run_find_devices_cmd(args: Namespace) -> int:
    """Find and list connected RTL-SDR devices."""
    output_json = getattr(args, "json", False)
    
    rtl_test = shutil.which("rtl_test")
    if not rtl_test:
        print("Error: rtl_test not found. Install rtl-sdr: sudo apt install rtl-sdr")
        return 1

    try:
        result = subprocess.run(
            ["rtl_test", "-t"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout + result.stderr
        
        # Parse devices from output
        devices = []
        
        for line in output.split("\n"):
            if line.startswith("Found") and "device(s)" in line:
                # Skip the found line
                continue
            elif line.startswith("  ") and ":" in line:
                # Device line: "  0:  Nooelec, NESDR SMArt v5, SN: 67411606"
                # Split on first colon only to get index
                first_colon_idx = line.index(":")
                idx = line[:first_colon_idx].strip()
                # Rest is the device description
                device_desc = line[first_colon_idx+1:].strip()
                
                device = {
                    "index": idx,
                    "name": device_desc,
                }
                
                # Extract serial if present (format: "Manufacturer, Model, SN: 67411606")
                if "SN:" in device_desc:
                    try:
                        serial = device_desc.split("SN:")[-1].strip()
                        device["serial"] = serial
                    except (ValueError, IndexError):
                        pass
                
                devices.append(device)
        
        if output_json:
            import json
            print(json.dumps({"devices": devices}, indent=2))
        else:
            if not devices:
                print("No RTL-SDR devices found.")
                if "No supported devices" in output or "Failed to open" in output:
                    print("\nNote: Device may be in use by readsb/dump1090.")
                    print("Check: systemctl status readsb")
                return 1
            
            print(f"Found {len(devices)} RTL-SDR device(s):\n")
            for dev in devices:
                print(f"  Index {dev['index']}: {dev['name']}")
                if "serial" in dev:
                    print(f"  → Use in readsb config: --device={dev['serial']}")
                print()
        
        return 0

    except subprocess.TimeoutExpired:
        print("Error: rtl_test timed out (device may be in use)")
        return 1
    except subprocess.SubprocessError as exc:
        print(f"Error running rtl_test: {exc}")
        return 1
