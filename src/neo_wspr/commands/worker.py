"""WSPR worker command implementation.

Runs the WSPR capture/decode/upload pipeline continuously.
"""

from __future__ import annotations

import logging
import time
from argparse import Namespace

from neo_core import config as config_module

LOG = logging.getLogger(__name__)


def run_worker(args: Namespace) -> int:
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

    capture.start()
    try:
        while capture.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("WSPR monitoring interrupted by user")
    finally:
        capture.stop()

    return 0

