"""ADS-B listen command implementation.

Monitors aircraft via dump1090/readsb and displays traffic.
"""

from __future__ import annotations

import logging
import time
from argparse import Namespace
import threading
from queue import Queue
from datetime import datetime, timezone

from neo_core import config as config_module
from neo_core.term import start_keyboard_listener, process_commands

LOG = logging.getLogger(__name__)


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

    # Determine JSON path from args or config
    json_path = getattr(args, "json_path", None)
    if not json_path and cfg:
        json_path = getattr(cfg, "adsb_json_path", None)
    if not json_path:
        json_path = "/run/dump1090-fa/aircraft.json"

    LOG.info("Starting ADS-B monitoring")
    LOG.info("Reading from: %s", json_path)
    LOG.info("ADS-B data directory: %s", data_dir)
    LOG.info("Application logs: %s", config_module.get_logs_dir("adsb"))

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
    }

    def _on_aircraft(aircraft_list):
        """Callback for aircraft updates."""
        nonlocal stats
        stats["total_aircraft"] = len(aircraft_list)
        for ac in aircraft_list:
            stats["unique_aircraft"].add(ac.hex_id)

        # Display aircraft
        if aircraft_list and not getattr(args, "quiet", False):
            _display_aircraft(aircraft_list)

    def _emit_version() -> None:
        """Display the neo-rx version."""
        try:
            import neo_rx
            version = getattr(neo_rx, "__version__", "unknown")
            print(f"\nneo-rx {version}\n", flush=True)
        except ImportError:
            print("\nneo-rx\n", flush=True)

    capture.add_callback(_on_aircraft)

    # Minimal keyboard listener for interactive commands
    stop_event = threading.Event()
    command_queue: "Queue[str]" = Queue()
    kb_thread = start_keyboard_listener(
        stop_event, command_queue, name="neo-rx-adsb-keyboard"
    )

    def _emit_summary() -> None:
        runtime = datetime.now(timezone.utc) - stats["start_time"]
        print(
            f"\nADS-B activity summary\n"
            f"Runtime: {runtime}\n"
            f"Current aircraft: {stats['total_aircraft']}\n"
            f"Unique aircraft seen: {len(stats['unique_aircraft'])}\n",
            flush=True,
        )

    capture.start()
    print("\nADS-B monitoring started. Press 's' for summary, 'q' to quit.\n")

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
