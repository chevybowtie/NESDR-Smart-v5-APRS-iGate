"""ADS-B listen command implementation.

Monitors aircraft via dump1090/readsb and displays traffic.
"""

from __future__ import annotations

import logging
import os
import time
from argparse import Namespace
import threading
from queue import Queue
from datetime import datetime, timezone
from pathlib import Path

from neo_core import config as config_module
from neo_core.term import start_keyboard_listener, process_commands

LOG = logging.getLogger(__name__)


def _find_aircraft_json() -> str:
    """Find aircraft.json from common ADS-B decoders.
    
    Checks readsb, dump1090-fa, and dump1090 in order.
    Returns the first existing file, or readsb default if none found.
    """
    candidates = [
        "/run/readsb/aircraft.json",
        "/run/dump1090-fa/aircraft.json",
        "/run/dump1090/aircraft.json",
    ]
    for path in candidates:
        if os.path.exists(path):
            LOG.debug("Found aircraft.json at: %s", path)
            return path
    LOG.debug("No aircraft.json found; defaulting to readsb location")
    return "/run/readsb/aircraft.json"


def run_listen(args: Namespace) -> int:
    """Start ADS-B monitoring loop: read dump1090 JSON → display → optional MQTT."""
    cfg_path = getattr(args, "config", None)
    cfg = None
    try:
        if cfg_path:
            cfg = config_module.load_config(cfg_path)
        else:
            cfg = config_module.load_config()
    except Exception:
        LOG.warning("Failed to load configuration; using defaults")

    data_dir = config_module.get_mode_data_dir("adsb")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Ensure per-mode file logging is active (in case CLI didn't configure it)
    try:
        log_dir = config_module.get_logs_dir("adsb")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "neo-rx.log"
        has_file_handler = False
        root_logger = logging.getLogger()
        for h in list(root_logger.handlers) + list(LOG.handlers):
            try:
                from logging import FileHandler

                if isinstance(h, FileHandler):
                    # If any FileHandler already targets our adsb log file, keep it
                    if getattr(h, "baseFilename", None) == str(log_file):
                        has_file_handler = True
                        break
            except Exception:
                continue
        if not has_file_handler:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fmt = logging.Formatter(
                "%(asctime)sZ %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
            )
            fmt.converter = time.gmtime
            fh.setFormatter(fmt)
            root_logger.addHandler(fh)
    except Exception:
        # Continue without file logging if setup fails
        pass

    # Determine JSON path from args or config, with auto-detection
    json_path = getattr(args, "json_path", None)
    if not json_path and cfg:
        json_path = getattr(cfg, "adsb_json_path", None)
    
    # If no explicit path or configured path doesn't exist, auto-detect
    if not json_path or not os.path.exists(json_path):
        if json_path:
            LOG.debug("Configured path %s not found; auto-detecting", json_path)
        json_path = _find_aircraft_json()
        LOG.info("Auto-detected aircraft.json: %s", json_path)

    LOG.info("Starting ADS-B monitoring")
    LOG.info("JSON source: %s", json_path)
    LOG.info("Note: ADS-B mode uses dump1090/readsb; neo-rx does not control the SDR")
    LOG.info("ADS-B data directory: %s", data_dir)
    LOG.info("Application logs: %s", config_module.get_logs_dir("adsb") / "neo-rx.log")

    # Validate JSON file exists and check freshness
    json_file = Path(json_path)
    if not json_file.exists():
        LOG.error("aircraft.json not found at %s", json_path)
        LOG.error("Is readsb/dump1090 running? Check: systemctl status readsb dump1090-fa")
        LOG.error("Detected decoders: systemctl list-units 'dump1090*' 'readsb*'")
        return 1

    try:
        stat = json_file.stat()
        age_sec = time.time() - stat.st_mtime
        LOG.info("aircraft.json: size=%d bytes, age=%.1fs", stat.st_size, age_sec)
        if age_sec > 10:
            LOG.warning(
                "aircraft.json hasn't been updated in %.1fs - decoder may not be running",
                age_sec,
            )
            LOG.warning("Check decoder status: journalctl -u readsb -u dump1090-fa --since '5 min ago'")
    except Exception as exc:
        LOG.warning("Could not stat %s: %s", json_path, exc)

    # Set up publisher if MQTT is enabled
    publisher = None
    if cfg and getattr(cfg, "mqtt_enabled", False):
        try:
            from neo_telemetry.mqtt_publisher import MqttPublisher

            publisher = MqttPublisher(
                host=getattr(cfg, "mqtt_host", "localhost"),
                port=getattr(cfg, "mqtt_port", 1883),
            )
            publisher.topic = getattr(cfg, "mqtt_topic", "neo_rx/adsb/aircraft")
            publisher.connect()
        except Exception:
            LOG.exception("Failed to create/connect publisher; continuing without")

    from neo_adsb.adsb.capture import AdsbCapture

    capture = AdsbCapture(
        json_path=json_path,
        poll_interval_s=getattr(args, "poll_interval", 1.0),
        data_dir=data_dir,
        publisher=publisher,
        station_config=cfg,
    )

    # Statistics tracking
    stats = {
        "total_aircraft": 0,
        "unique_aircraft": set(),
        "start_time": datetime.now(timezone.utc),
        "display_paused": False,
        "pause_until": 0.0,
    }

    def _on_aircraft(aircraft_list):
        """Callback for aircraft updates."""
        nonlocal stats
        stats["total_aircraft"] = len(aircraft_list)
        for ac in aircraft_list:
            stats["unique_aircraft"].add(ac.hex_id)

        # Display aircraft only if not paused
        if aircraft_list and not getattr(args, "quiet", False):
            if not stats["display_paused"] and time.monotonic() > stats["pause_until"]:
                _display_aircraft(aircraft_list)

    def _emit_version() -> None:
        """Display the neo-rx version."""
        # Pause display updates for 3 seconds
        stats["pause_until"] = time.monotonic() + 3.0
        try:
            import neo_rx
            version = getattr(neo_rx, "__version__", "unknown")
            print(f"\n{'=' * 40}\nneo-rx {version}\n{'=' * 40}\n", flush=True)
        except ImportError:
            print(f"\n{'=' * 40}\nneo-rx\n{'=' * 40}\n", flush=True)

    capture.add_callback(_on_aircraft)

    # Minimal keyboard listener for interactive commands
    stop_event = threading.Event()
    command_queue: "Queue[str]" = Queue()
    kb_thread = start_keyboard_listener(
        stop_event, command_queue, name="neo-rx-adsb-keyboard"
    )

    def _emit_summary() -> None:
        # Pause display updates for 5 seconds
        stats["pause_until"] = time.monotonic() + 5.0
        runtime = datetime.now(timezone.utc) - stats["start_time"]
        print(
            f"\n{'=' * 50}\n"
            f"ADS-B activity summary\n"
            f"Runtime: {runtime}\n"
            f"Current aircraft: {stats['total_aircraft']}\n"
            f"Unique aircraft seen: {len(stats['unique_aircraft'])}\n"
            f"{'=' * 50}\n",
            flush=True,
        )

    capture.start()
    print("\nADS-B monitoring started. Press 's' for summary, 'q' to quit.\n")
    print("View live traffic: http://localhost/tar1090/, view your contribution: https://adsbexchange.com/myip/\n", flush=True)

    try:
        while capture.is_running() and not stop_event.is_set():
            time.sleep(1)
            process_commands(
                command_queue,
                {
                    "q": lambda: (
                        print("\nExiting ADS-B monitor...\n", flush=True),
                        stop_event.set(),
                        capture.stop(),
                    ),
                    "v": _emit_version,
                    "s": _emit_summary,
                },
            )
    except KeyboardInterrupt:
        LOG.info("ADS-B monitoring interrupted by user")
    finally:
        capture.stop()
        if kb_thread and kb_thread.is_alive():
            kb_thread.join(timeout=1)

    return 0


def _display_aircraft(aircraft_list: list) -> None:
    """Display current aircraft in a table format."""
    # Clear and redraw - simple display without curses
    header = f"{'ICAO':<8} {'Flight':<10} {'Alt(ft)':<8} {'Spd(kt)':<8} {'Track':<6} {'Lat':>10} {'Lon':>11} {'RSSI':>6}"
    print("\033[2J\033[H")  # Clear screen and move cursor to top
    print(f"ADS-B Monitor - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}")
    print("Map: http://localhost/tar1090/, your data: https://adsbexchange.com/myip/")
    print("-" * 80)
    print(header)
    print("-" * 80)

    # Sort by altitude descending
    sorted_ac = sorted(
        aircraft_list,
        key=lambda x: x.altitude_ft if x.altitude_ft else 0,
        reverse=True,
    )

    for ac in sorted_ac[:20]:  # Show top 20 by altitude
        icao = ac.hex_id or ""
        flight = (ac.flight or "").strip()
        alt = str(ac.altitude_ft) if ac.altitude_ft else ""
        spd = f"{ac.ground_speed_kt:.0f}" if ac.ground_speed_kt else ""
        track = f"{ac.track_deg:.0f}" if ac.track_deg else ""
        lat = f"{ac.latitude:.4f}" if ac.latitude else ""
        lon = f"{ac.longitude:.4f}" if ac.longitude else ""
        rssi = f"{ac.rssi_db:.1f}" if ac.rssi_db else ""
        print(f"{icao:<8} {flight:<10} {alt:<8} {spd:<8} {track:<6} {lat:>10} {lon:>11} {rssi:>6}")

    print("-" * 80)
    print(f"Total aircraft: {len(aircraft_list)} | Press 's' for summary, 'q' to quit")
