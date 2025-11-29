"""WSPR listen command implementation.

Runs the WSPR capture/decode/upload pipeline continuously.
"""

from __future__ import annotations

import logging
import time
from argparse import Namespace
import sys
import threading
from queue import Queue, Empty

from neo_core import config as config_module
from neo_core.term import start_keyboard_listener, process_commands
from pathlib import Path
from datetime import datetime, timezone

LOG = logging.getLogger(__name__)


def run_listen(args: Namespace) -> int:
    """Start WSPR monitoring loop: capture → decode → upload."""
    cfg_path = getattr(args, "config", None)
    cfg = None
    try:
        if cfg_path:
            cfg = config_module.load_config(cfg_path)
        else:
            cfg = config_module.load_config()
    except Exception:
        LOG.warning("Failed to load configuration; using defaults")

    data_dir = config_module.get_mode_data_dir("wspr")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Use per-run directories for artifacts (spots, queue, temp files)
    run_label = getattr(args, "run_label", None)
    run_dir = config_module.get_wspr_runs_dir(run_label)
    run_dir.mkdir(parents=True, exist_ok=True)

    LOG.info("Starting WSPR monitoring")
    LOG.info("WSPR run directory: %s", run_dir)
    LOG.info("WSPR spots will be saved to: %s", run_dir / "wspr_spots.jsonl")
    LOG.info("Application logs: %s", config_module.get_logs_dir("wspr"))

    # Set up publisher if MQTT is enabled
    publisher = None
    if cfg and getattr(cfg, "mqtt_enabled", False):
        try:
            from neo_wspr.wspr.publisher import make_publisher_from_config

            publisher = make_publisher_from_config(cfg)
            if publisher:
                publisher.topic = getattr(cfg, "mqtt_topic", "neo_rx/wspr/spots")
                publisher.connect()
        except Exception:
            LOG.exception("Failed to create/connect publisher; continuing without")

    # Set up uploader if enabled
    uploader = None
    if cfg and getattr(cfg, "wspr_uploader_enabled", False):
        from neo_wspr.wspr.uploader import WsprUploader

        queue_path = run_dir / "wspr_upload_queue.jsonl"
        uploader = WsprUploader(queue_path=queue_path)
        LOG.info("WSPR uploader queue enabled: %s", queue_path)

    # Handle band selection
    band_mapping = {
        "80m": 3_594_000,
        "40m": 7_038_600,
        "30m": 10_140_200,
        "20m": 14_095_600,
        "10m": 28_124_600,
        "6m": 50_294_800,
        "2m": 144_489_000,
        "70cm": 432_500_000,
    }

    selected_band = getattr(args, "band", None)
    if selected_band:
        bands = [band_mapping.get(selected_band, 14_095_600)]
        LOG.info("Monitoring only %s band (%s Hz)", selected_band, bands[0])
    else:
        bands = getattr(cfg, "wspr_bands_hz", None) if cfg else None

    duration = getattr(cfg, "wspr_capture_duration_s", 119) if cfg else 119
    upconverter_enabled = getattr(cfg, "upconverter_enabled", False) if cfg else False
    upconverter_offset = getattr(cfg, "upconverter_lo_offset_hz", None) if cfg else None

    from neo_wspr.wspr.capture import WsprCapture

    capture = WsprCapture(
        bands_hz=bands,
        capture_duration_s=duration,
        data_dir=run_dir,
        publisher=publisher,
        upconverter_enabled=upconverter_enabled,
        upconverter_offset_hz=upconverter_offset,
        station_config=cfg,
        uploader=uploader,
    )

    # Minimal keyboard listener for interactive commands
    stop_event = threading.Event()
    command_queue: "Queue[str]" = Queue()
    kb_thread = start_keyboard_listener(stop_event, command_queue, name="neo-rx-wspr-keyboard")

    def _emit_wspr_summary() -> None:
        spots_path = run_dir / "wspr_spots.jsonl"
        if not spots_path.exists():
            print("\nNo WSPR spots file available yet; try again after captures.\n", flush=True)
            return
        try:
            total = 0
            latest: float | None = None
            with spots_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    total += 1
                    latest = float(spots_path.stat().st_mtime)
            ts = datetime.fromtimestamp(latest or spots_path.stat().st_mtime, tz=timezone.utc)
            print(
                f"\nWSPR activity summary\nSpots file: {spots_path}\nTotal spots: {total}\nLast update: {ts.strftime('%Y-%m-%d %H:%MZ')}\n",
                flush=True,
            )
        except Exception:
            pass

    capture.start()
    try:
        while capture.is_running() and not stop_event.is_set():
            time.sleep(1)
            process_commands(
                command_queue,
                {
                    "q": lambda: (print("\nExiting WSPR monitor...\n", flush=True), stop_event.set(), capture.stop()),
                    "v": lambda: (print(f"\nneo-rx {__import__('neo_rx').__version__}\n", flush=True) if hasattr(__import__('neo_rx'), '__version__') else print("\nneo-rx\n", flush=True)),
                    "s": _emit_wspr_summary,
                },
            )
    except KeyboardInterrupt:
        LOG.info("WSPR monitoring interrupted by user")
    finally:
        capture.stop()
        if kb_thread and kb_thread.is_alive():
            kb_thread.join(timeout=1)

    return 0
