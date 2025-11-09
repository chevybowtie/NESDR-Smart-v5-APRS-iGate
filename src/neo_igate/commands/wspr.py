"""CLI command handler for WSPR operations (skeleton).

Provides a single entrypoint `run_wspr` used by `neo-igate wspr`.
"""

from __future__ import annotations

import logging
from argparse import Namespace
from typing import Optional

from neo_igate import config as config_module
from neo_igate.wspr.capture import WsprCapture
from neo_igate.wspr.decoder import WsprDecoder
from neo_igate.wspr.publisher import make_publisher_from_config

LOG = logging.getLogger(__name__)


def _load_config_if_present(path: Optional[str]):
    if not path:
        try:
            return config_module.load_config()
        except Exception:
            return None
    try:
        return config_module.load_config(path)
    except Exception:
        LOG.exception("Failed to load configuration from %s", path)
        return None


def run_wspr(args: Namespace) -> int:
    """Handle top-level `wspr` CLI invocations.

    Implement a minimal start flow: load configuration (if available),
    instantiate capture and decoder objects, and start the capture (stub).
    This wiring prepares the ground for hooking the decoder and uploader
    in subsequent milestones.
    """
    cfg = _load_config_if_present(getattr(args, "config", None))

    if getattr(args, "start", False):
        LOG.info("Starting WSPR worker")
        capture = WsprCapture(config=cfg)
        decoder = WsprDecoder(options={})
        capture.start()
        publisher = None
        try:
            if cfg is not None:
                try:
                    publisher = make_publisher_from_config(cfg)
                    if publisher is not None:
                        publisher.connect()
                except Exception:
                    LOG.exception("Failed to create/connect publisher; continuing without it")

                import signal

                LOG.info("WSPR capture started. Running decoder subprocess (if available)...")

                old_int = signal.getsignal(signal.SIGINT)
                old_term = signal.getsignal(signal.SIGTERM)

                def _raise_keyboard(signum, frame):
                    raise KeyboardInterrupt()

                signal.signal(signal.SIGINT, _raise_keyboard)
                signal.signal(signal.SIGTERM, _raise_keyboard)

                try:
                    for spot in decoder.run_wsprd_subprocess():
                        LOG.info("Decoded spot: %s", spot)
                        try:
                            if publisher is not None:
                                topic = cfg.mqtt_topic if (cfg and cfg.mqtt_topic) else "neo_igate/wspr/spots"
                                publisher.publish(topic, spot)
                        except Exception:
                            LOG.exception("Failed publishing spot; continuing")

                except KeyboardInterrupt:
                    LOG.info("WSPR worker interrupted by user")
                finally:
                    # restore original handlers
                    try:
                        signal.signal(signal.SIGINT, old_int)
                        signal.signal(signal.SIGTERM, old_term)
                    except Exception:
                        pass
        finally:
            if publisher is not None:
                try:
                    publisher.close()
                except Exception:
                    LOG.exception("Error closing publisher")
            capture.stop()
            LOG.info("WSPR worker stopped")
        return 0

    if getattr(args, "scan", False):
        LOG.info("Requested WSPR band-scan (stub)")
        return 0

    if getattr(args, "diagnostics", False):
        LOG.info("Requested WSPR diagnostics (stub)")
        return 0

    if getattr(args, "calibrate", False):
        LOG.info("Requested WSPR calibration (stub)")
        return 0

    if getattr(args, "upload", False):
        LOG.info("Requested WSPR upload (stub)")
        return 0

    LOG.info("No action specified for wspr; nothing to do")
    return 0


__all__ = ["run_wspr"]
