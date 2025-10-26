"""Runtime command implementation for the APRS iGate listener."""

from __future__ import annotations

import logging
import signal
import subprocess
import threading
import time
from argparse import Namespace
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

from nesdr_igate import config as config_module
from nesdr_igate.aprs.ax25 import AX25DecodeError, kiss_payload_to_tnc2  # type: ignore[import]
from nesdr_igate.aprs.aprsis_client import (  # type: ignore[import]
    APRSISClient,
    APRSISClientError,
    APRSISConfig,
    RetryBackoff,
)
from nesdr_igate.aprs.kiss_client import KISSClient, KISSClientConfig, KISSClientError  # type: ignore[import]
from nesdr_igate.radio.capture import AudioCaptureError, RtlFmAudioCapture, RtlFmConfig  # type: ignore[import]

try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover
    import importlib_metadata  # type: ignore[no-redef]

AUDIO_SAMPLE_RATE = 22_050
_AUDIO_CHUNK_BYTES = 4096
_SOFTWARE_NAME = "nesdr-igate"

try:
    _SOFTWARE_VERSION = importlib_metadata.version("nesdr-igate")
except (
    importlib_metadata.PackageNotFoundError
):  # pragma: no cover - dev install fallback
    _SOFTWARE_VERSION = "0.0.0"


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def run_listen(args: Namespace) -> int:
    """Run the igate listening loop."""
    config_path = config_module.resolve_config_path(getattr(args, "config", None))
    try:
        station_config = config_module.load_config(config_path)
    except FileNotFoundError:
        logger.error(
            "Config not found at %s; run `nesdr-igate setup` first.", config_path
        )
        return 1
    except ValueError as exc:
        logger.error("Config invalid: %s", exc)
        return 1

    direwolf_conf = _resolve_direwolf_config(config_path.parent)
    if direwolf_conf is None:
        logger.error(
            "Direwolf configuration missing; rerun setup to render direwolf.conf"
        )
        return 1

    rtl_config = RtlFmConfig(
        frequency_hz=station_config.center_frequency_hz,
        sample_rate=AUDIO_SAMPLE_RATE,
        gain=station_config.gain,
        ppm=station_config.ppm_correction or 0,
        device_index=0,
    )

    capture = RtlFmAudioCapture(rtl_config)
    direwolf_proc: subprocess.Popen[bytes] | None = None
    audio_thread: threading.Thread | None = None
    audio_errors: "Queue[Exception]" = Queue()

    aprs_client: Optional[APRSISClient] = None
    aprs_enabled = not getattr(args, "no_aprsis", False)
    aprs_config: Optional[APRSISConfig] = None
    aprs_backoff = RetryBackoff(base_delay=2.0, max_delay=120.0, multiplier=2.0)
    aprs_forwarded = 0
    aprs_failed = 0

    stats_interval = 60.0
    next_stats_report = time.monotonic() + stats_interval

    stop_event = threading.Event()

    def _pump_audio() -> None:
        try:
            while not stop_event.is_set():
                chunk = capture.read(_AUDIO_CHUNK_BYTES)
                if not chunk:
                    continue
                if direwolf_proc is None or direwolf_proc.stdin is None:
                    continue
                try:
                    direwolf_proc.stdin.write(chunk)
                    direwolf_proc.stdin.flush()
                except (
                    BrokenPipeError
                ) as exc:  # pragma: no cover - depends on direwolf exit timing
                    audio_errors.put(exc)
                    break
        except Exception as exc:  # pragma: no cover - defensive
            audio_errors.put(exc)

    def _cleanup() -> None:
        nonlocal aprs_client
        stop_event.set()
        capture.stop()
        if audio_thread and audio_thread.is_alive():
            audio_thread.join(timeout=1)
            if audio_thread.is_alive():
                logger.debug("Audio pump thread still running after timeout")
        if aprs_client is not None:
            aprs_client.close()
            aprs_client = None
        if direwolf_proc is not None:
            if direwolf_proc.stdin:
                try:
                    direwolf_proc.stdin.close()
                except OSError:
                    pass
            direwolf_proc.terminate()
            try:
                direwolf_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                direwolf_proc.kill()

    previous_signals = {
        signal.SIGINT: signal.getsignal(signal.SIGINT),
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
    }

    def _restore_signals() -> None:
        for sig, previous in previous_signals.items():
            signal.signal(sig, previous)

    def _handle_shutdown(signum, frame):  # type: ignore[override]
        stop_event.set()
        raise KeyboardInterrupt

    for sig in previous_signals:
        signal.signal(sig, _handle_shutdown)

    try:
        logger.info("Starting rtl_fm capture...")
        capture.start()
    except AudioCaptureError as exc:
        _restore_signals()
        logger.error("Audio capture failed: %s", exc)
        return 1

    try:
        direwolf_cmd = [
            "direwolf",
            "-c",
            str(direwolf_conf),
            "-r",
            str(rtl_config.sample_rate),
            "-t",
            "0",
            "-",
        ]
        direwolf_proc = subprocess.Popen(
            direwolf_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Direwolf launched (PID %s)", direwolf_proc.pid)
    except OSError as exc:
        capture.stop()
        _restore_signals()
        logger.error("Failed to start Direwolf: %s", exc)
        return 1

    audio_thread = threading.Thread(
        target=_pump_audio, name="rtl_fm_audio", daemon=True
    )
    audio_thread.start()

    client = KISSClient(
        KISSClientConfig(
            host=station_config.kiss_host,
            port=station_config.kiss_port,
            timeout=2.0,
        )
    )

    if not _wait_for_kiss(client, attempts=10, delay=0.5):
        logger.error(
            "Unable to connect to Direwolf KISS at %s:%s.",
            station_config.kiss_host,
            station_config.kiss_port,
        )
        _cleanup()
        _restore_signals()
        return 1

    if aprs_enabled:
        aprs_config = APRSISConfig(
            host=station_config.aprs_server,
            port=station_config.aprs_port,
            callsign=station_config.callsign,
            passcode=station_config.passcode,
            software_name=_SOFTWARE_NAME,
            software_version=_SOFTWARE_VERSION,
        )
    else:
        logger.info("APRS-IS uplink disabled (receive-only mode)")

    logger.info("Connected to Direwolf KISS port; awaiting frames...")
    frame_count = 0

    def _attempt_aprs_connect() -> None:
        nonlocal aprs_client
        if not aprs_enabled or aprs_config is None:
            return
        if aprs_client is not None:
            return
        if not aprs_backoff.ready():
            return
        try:
            candidate = APRSISClient(aprs_config)
            candidate.connect()
            aprs_client = candidate
            aprs_backoff.record_success()
            logger.info(
                "Connected to APRS-IS %s:%s",
                aprs_config.host,
                aprs_config.port,
            )
        except APRSISClientError as exc:
            delay = aprs_backoff.record_failure()
            logger.warning(
                "APRS-IS connection failed: %s; retrying in %ss", exc, int(delay)
            )

    _attempt_aprs_connect()

    try:
        while True:
            _attempt_aprs_connect()
            if stop_event.is_set():
                break
            try:
                frame = client.read_frame(timeout=1.0)
            except TimeoutError:
                _report_audio_error(audio_errors)
                continue
            except KISSClientError as exc:
                logger.error("KISS client error: %s", exc)
                return 1

            try:
                tnc2_packet = kiss_payload_to_tnc2(frame.payload)
            except AX25DecodeError as exc:
                logger.warning("Skipping undecodable frame: %s", exc)
                continue

            frame_count += 1
            _display_frame(frame_count, frame.port, tnc2_packet)

            if aprs_client is not None:
                try:
                    aprs_client.send_packet(tnc2_packet)
                    aprs_forwarded += 1
                except APRSISClientError as exc:
                    aprs_failed += 1
                    logger.warning(
                        "APRS-IS transmission error: %s; scheduling reconnect",
                        exc,
                    )
                    aprs_client.close()
                    aprs_client = None
                    aprs_backoff.reset()

            if getattr(args, "once", False):
                stop_event.set()
                break

            _report_audio_error(audio_errors)

            if (
                not getattr(args, "once", False)
                and time.monotonic() >= next_stats_report
            ):
                logger.info(
                    "[stats] frames=%s aprs_ok=%s aprs_fail=%s",
                    frame_count,
                    aprs_forwarded,
                    aprs_failed,
                )
                next_stats_report = time.monotonic() + stats_interval
    except KeyboardInterrupt:
        logger.info("Stopping listener...")
    finally:
        client.close()
        _cleanup()
        _restore_signals()

    if aprs_enabled:
        logger.info(
            "Frames processed: %s (APRS-IS ok=%s, failed=%s)",
            frame_count,
            aprs_forwarded,
            aprs_failed,
        )
    else:
        logger.info("Frames processed: %s", frame_count)
    return 0


def _resolve_direwolf_config(config_dir: Path) -> Optional[Path]:
    candidate = config_dir / "direwolf.conf"
    if candidate.exists():
        return candidate
    default_path = config_module.get_config_dir() / "direwolf.conf"
    return default_path if default_path.exists() else None


def _wait_for_kiss(client: KISSClient, *, attempts: int, delay: float) -> bool:
    for attempt in range(attempts):
        try:
            client.connect()
            return True
        except KISSClientError:
            time.sleep(delay)
    return False


def _display_frame(count: int, port: int, tnc2_line: str) -> None:
    snippet = tnc2_line
    if len(snippet) > 120:
        snippet = snippet[:117] + "…"
    logger.info("[%06d] port=%s %s", count, port, snippet)


def _report_audio_error(queue: "Queue[Exception]") -> None:
    try:
        exc = queue.get_nowait()
    except Empty:
        return
    logger.error("Audio pipeline error: %s", exc)
