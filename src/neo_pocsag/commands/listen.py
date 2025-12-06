"""POCSAG listen command implementation.

Monitors pager messages via RTL-SDR and multimon-ng.
"""

from __future__ import annotations

import logging
import time
from argparse import Namespace
import threading
from queue import Queue
from datetime import datetime, timezone
from pathlib import Path

from neo_core import config as config_module
from neo_core.term import start_keyboard_listener, process_commands

LOG = logging.getLogger(__name__)


def run_listen(args: Namespace) -> int:
    """Start POCSAG monitoring loop."""
    cfg_path = getattr(args, "config", None)
    cfg = None
    try:
        if cfg_path:
            cfg = config_module.load_config(cfg_path)
        else:
            cfg = config_module.load_config()
    except Exception:
        LOG.warning("Failed to load configuration; using defaults")

    data_dir = config_module.get_mode_data_dir("pocsag")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Ensure per-mode file logging is active
    try:
        log_dir = config_module.get_logs_dir("pocsag")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "neo-rx.log"
        has_file_handler = False
        root_logger = logging.getLogger()
        for h in list(root_logger.handlers) + list(LOG.handlers):
            try:
                from logging import FileHandler
                if isinstance(h, FileHandler):
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
        pass

    # Get frequency from args or config
    frequency_hz = getattr(args, "frequency", 152_840_000)
    if cfg and hasattr(cfg, "pocsag_frequency_hz"):
        frequency_hz = getattr(cfg, "pocsag_frequency_hz", frequency_hz)

    LOG.info("Starting POCSAG monitoring at %d Hz", frequency_hz)
    LOG.info("POCSAG data directory: %s", data_dir)
    LOG.info("Application logs: %s", config_module.get_logs_dir("pocsag") / "neo-rx.log")

    # Set up publisher if MQTT is enabled
    publisher = None
    if cfg and getattr(cfg, "mqtt_enabled", False):
        try:
            from neo_telemetry.mqtt_publisher import MqttPublisher
            publisher = MqttPublisher(
                host=getattr(cfg, "mqtt_host", "localhost"),
                port=getattr(cfg, "mqtt_port", 1883),
            )
            publisher.topic = getattr(cfg, "mqtt_topic", "neo_rx/pocsag/messages")
            LOG.info(
                "MQTT: connecting to %s:%s, topic=%s",
                getattr(cfg, "mqtt_host", "localhost"),
                getattr(cfg, "mqtt_port", 1883),
                publisher.topic,
            )
            publisher.connect()
            LOG.info("MQTT: connected; publishing enabled")
        except Exception:
            LOG.exception("Failed to create/connect publisher; continuing without")

    from neo_pocsag.pocsag.capture import PocsagCapture  # type: ignore[import]

    capture = PocsagCapture(
        frequency_hz=frequency_hz,
        gain=getattr(args, "gain", None),
        ppm=getattr(args, "ppm", 0),
        device_index=getattr(args, "device_index", 0),
        data_dir=data_dir,
        publisher=publisher,
    )

    # Statistics tracking
    stats = {
        "total_messages": 0,
        "unique_addresses": 0,
        "start_time": datetime.now(timezone.utc),
    }

    def _on_message(message):
        """Callback for message updates."""
        nonlocal stats
        stats["total_messages"] += 1
        stats["unique_addresses"] = len(capture.get_stats().unique_addresses)

    capture.add_callback(_on_message)

    # Minimal keyboard listener
    stop_event = threading.Event()
    command_queue: "Queue[str]" = Queue()
    kb_thread = start_keyboard_listener(
        stop_event, command_queue, name="neo-rx-pocsag-keyboard"
    )

    def _emit_version() -> None:
        """Display the neo-rx version."""
        try:
            import neo_rx
            version = getattr(neo_rx, "__version__", "unknown")
            print(f"\n{'=' * 40}\nneo-rx {version}\n{'=' * 40}\n", flush=True)
        except ImportError:
            print(f"\n{'=' * 40}\nneo-rx\n{'=' * 40}\n", flush=True)

    def _emit_summary() -> None:
        """Display POCSAG activity summary."""
        runtime = datetime.now(timezone.utc) - stats["start_time"]
        print(
            f"\n{'=' * 50}\n"
            f"POCSAG activity summary\n"
            f"Runtime: {runtime}\n"
            f"Total messages: {stats['total_messages']}\n"
            f"Unique addresses: {stats['unique_addresses']}\n"
            f"{'=' * 50}\n",
            flush=True,
        )

    capture.start()
    print("\nPOCSAG monitoring started. Press 's' for summary, 'q' to quit.\n")
    print("Listening for pager messages...\n", flush=True)

    try:
        while capture.is_running() and not stop_event.is_set():
            time.sleep(1)
            process_commands(
                command_queue,
                {
                    "q": lambda: (
                        print("\nExiting POCSAG monitor...\n", flush=True),
                        stop_event.set(),
                        capture.stop(),
                    ),
                    "v": _emit_version,
                    "s": _emit_summary,
                },
            )
    except KeyboardInterrupt:
        LOG.info("POCSAG monitoring interrupted by user")
    finally:
        capture.stop()
        if kb_thread and kb_thread.is_alive():
            kb_thread.join(timeout=1)

    return 0