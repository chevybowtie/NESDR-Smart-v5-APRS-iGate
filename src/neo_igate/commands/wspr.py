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
        decoder = WsprDecoder(options={})
        publisher = None
        try:
            # Respect CLI override when present; otherwise fall back to config
            mqtt_override = getattr(args, "mqtt", None)
            mqtt_enabled = (
                mqtt_override
                if mqtt_override is not None
                else (cfg.mqtt_enabled if cfg is not None else False)
            )
            if mqtt_enabled:
                try:
                    if cfg is None:
                        # No config available: construct a default MQTT publisher
                        from neo_igate.telemetry.mqtt_publisher import MqttPublisher

                        publisher = MqttPublisher(host="127.0.0.1", port=1883)
                    else:
                        publisher = make_publisher_from_config(cfg)

                    if publisher is not None:
                        # prefer configured topic when present
                        publisher.topic = cfg.mqtt_topic if (cfg and cfg.mqtt_topic) else "neo_igate/wspr/spots"
                        publisher.connect()
                except Exception:
                    LOG.exception("Failed to create/connect publisher; continuing without it")
            else:
                LOG.debug("MQTT disabled by config/CLI; no publisher created")

            # create capture with publisher so run_capture_cycle (if used) will publish
            capture = WsprCapture(
                bands_hz=cfg.wspr_bands_hz if (cfg and cfg.wspr_bands_hz) else None,
                capture_duration_s=(cfg.wspr_capture_duration_s if cfg else 120),
                publisher=publisher,
            )
            capture.start()

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
        LOG.info("Running WSPR band-scan")
        from neo_igate.wspr import scan as wspr_scan
        import shutil
        import subprocess
        import time

        bands = []
        if cfg is not None and cfg.wspr_bands_hz:
            bands = cfg.wspr_bands_hz
        else:
            bands = [14_080_000, 7_080_000, 3_572_000]

        duration = cfg.wspr_capture_duration_s if cfg is not None else 120

        def _capture_fn(band_hz: int, dur: int):
            # Try to run `wsprd` and capture stdout lines for `dur` seconds.
            if shutil.which("wsprd") is None:
                LOG.warning("wsprd not found; skipping live capture for band %s", band_hz)
                return []
            cmd = ["wsprd"]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            except Exception:
                LOG.exception("Failed to start wsprd for band %s", band_hz)
                return []

            lines = []
            start = time.time()
            try:
                assert proc.stdout is not None
                while time.time() - start < dur:
                    line = proc.stdout.readline()
                    if not line:
                        if proc.poll() is not None:
                            break
                        continue
                    lines.append(line)
            finally:
                try:
                    proc.terminate()
                except Exception:
                    pass
            return lines

        reports = wspr_scan.scan_bands(bands, _capture_fn, duration)
        # Emit either JSON output (machine-readable) or human-friendly log lines
        if getattr(args, "json", False):
            import json

            print(json.dumps(reports, indent=2, default=str))
            return 0

        # print ranked report
        for r in reports:
            LOG.info(
                "Band %s: decodes=%s dec/min=%.2f median_snr=%s max_snr=%s unique_calls=%s",
                r.get("band_hz"),
                r.get("band_decodes"),
                r.get("decodes_per_min", 0.0),
                r.get("median_snr_db"),
                r.get("max_snr_db"),
                r.get("unique_calls"),
            )
        return 0

    if getattr(args, "diagnostics", False):
        LOG.info("Requested WSPR diagnostics")
        from pathlib import Path
        from neo_igate.wspr import diagnostics as wspr_diag

        # attempt to load recent spots from data dir (best-effort)
        data_dir = config_module.get_data_dir() if cfg is not None else Path("./data")
        spots_file = data_dir / "wspr_spots.jsonl"
        spots = []
        try:
            from neo_igate.wspr.calibrate import load_spots_from_jsonl

            spots = load_spots_from_jsonl(spots_file)
        except Exception:
            LOG.exception("Failed to load spots for diagnostics")

        hint = wspr_diag.detect_upconverter_hint(spots)
        LOG.info("Upconverter diagnostic: %s", hint)
        return 0
        return 0

    if getattr(args, "calibrate", False):
        LOG.info("Requested WSPR calibration")
        from pathlib import Path
        from neo_igate.wspr.calibrate import load_spots_from_jsonl, estimate_offset_from_spots, apply_ppm_to_radio

        # Determine spots file: CLI override -> config data dir -> local data dir
        spots_path = None
        if getattr(args, "spots_file", None):
            spots_path = Path(getattr(args, "spots_file"))
        elif cfg is not None:
            spots_path = config_module.get_data_dir() / "wspr_spots.jsonl"
        else:
            spots_path = Path("./data/wspr_spots.jsonl")

        spots = load_spots_from_jsonl(spots_path)
        if not spots:
            LOG.warning("No spots found in %s; cannot calibrate", spots_path)
            return 1

        # expected frequency: CLI override > config first band (if present)
        expected_freq = getattr(args, "expected_freq", None)
        if expected_freq is None and cfg is not None and cfg.wspr_bands_hz:
            expected_freq = cfg.wspr_bands_hz[0]

        try:
            result = estimate_offset_from_spots(spots, expected_freq)
        except Exception:
            LOG.exception("Failed to estimate offset from spots")
            return 1

        LOG.info("Calibration result: median_obs=%.0f Hz offset=%.1f Hz ppm=%.3f count=%d",
                 result.get("median_observed_freq_hz", 0.0),
                 result.get("offset_hz", 0.0),
                 result.get("ppm", 0.0),
                 result.get("count", 0),
                 )

        if getattr(args, "apply", False):
            ppm = result.get("ppm", 0.0)
            try:
                # apply to radio (stub)
                apply_ppm_to_radio(ppm)
                LOG.info("Applied ppm=%.3f to radio (stub)", ppm)

                # optionally persist into config
                if bool(getattr(args, "write_config", False)):
                    from neo_igate.wspr.calibrate import persist_ppm_to_config

                    cfg_path = getattr(args, "config", None)
                    persist_ppm_to_config(ppm, config_path=cfg_path)
                    # Also print a CLI-facing message with the saved config path
                    try:
                        saved_path = cfg_path or config_module.resolve_config_path()
                    except Exception:
                        saved_path = cfg_path or "<default>"
                    print(f"Saved ppm correction to: {saved_path}")
                    LOG.info("Persisted ppm=%.3f to config %s", ppm, saved_path)
            except Exception:
                LOG.exception("Failed applying ppm to radio or persisting")
                return 1

        return 0

    if getattr(args, "upload", False):
        LOG.info("Requested WSPR upload (stub)")
        return 0

    LOG.info("No action specified for wspr; nothing to do")
    return 0


__all__ = ["run_wspr"]
