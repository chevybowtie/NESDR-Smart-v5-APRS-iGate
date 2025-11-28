"""Runtime command implementation for the APRS iGate listener."""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from argparse import Namespace
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

from neo_core import config as config_module
from neo_aprs.aprs.ax25 import AX25DecodeError, kiss_payload_to_tnc2  # type: ignore[import]
from neo_aprs.aprs.aprsis_client import (  # type: ignore[import]
    APRSISClient,
    APRSISClientError,
    APRSISConfig,
    RetryBackoff,
)
from neo_aprs.aprs.kiss_client import KISSClient, KISSClientConfig, KISSClientError  # type: ignore[import]
from neo_core.radio.capture import AudioCaptureError, RtlFmAudioCapture, RtlFmConfig  # type: ignore[import]

try:
    from neo_rx import __version__ as _SOFTWARE_VERSION
except ImportError:
    _SOFTWARE_VERSION = "0.2.2"


AUDIO_SAMPLE_RATE = 22_050
_AUDIO_CHUNK_BYTES = 4096
_SOFTWARE_NAME = "neo-rx"

# _SOFTWARE_VERSION is provided by the package-level __version__ value.


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Capture the real Thread class to avoid tests monkeypatching threading.Thread
# from inadvertently running the keyboard listener synchronously.
_REAL_THREAD = threading.Thread


def run_listen(args: Namespace) -> int:
    """Run the igate listening loop."""
    config_path = config_module.resolve_config_path(getattr(args, "config", None))
    try:
        station_config = config_module.load_config(config_path)
    except FileNotFoundError:
        logger.error(
            "Config not found at %s; run `neo-rx aprs setup` first.", config_path
        )
        return 1
    except ValueError as exc:
        logger.error("Config invalid: %s", exc)
        return 1

    logger.info(
        "neo-rx v%s — starting listener (callsign=%s, aprs_server=%s:%s)",
        _SOFTWARE_VERSION,
        station_config.callsign,
        station_config.aprs_server,
        station_config.aprs_port,
    )

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
    command_queue: "Queue[str]" = Queue()
    keyboard_thread = _start_keyboard_listener(stop_event, command_queue)
    summary_log_path = config_module.get_logs_dir("aprs") / "neo-rx.log"

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
                except OSError as exc:
                    logger.debug("Unable to close Direwolf stdin: %s", exc)
            direwolf_proc.terminate()
            try:
                direwolf_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                direwolf_proc.kill()
        if keyboard_thread and keyboard_thread.is_alive():
            keyboard_thread.join(timeout=1)

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
            logger.info("Press `s` at any time for a 24h station summary.")
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
                _handle_keyboard_commands(command_queue, summary_log_path)
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
                    # Apply configured software TOCALL for packets that were
                    # clearly originated by this station (safe default: only
                    # when SRC matches our configured callsign). This avoids
                    # rewriting DST for RF-forwarded traffic.
                    if (
                        getattr(station_config, "software_tocall", None)
                        and _get_source_callsign(tnc2_packet) == station_config.callsign
                    ):
                        tnc2_to_send = _apply_software_tocall(
                            tnc2_packet, station_config.software_tocall
                        )
                    else:
                        tnc2_to_send = tnc2_packet

                    tnc2_to_send = _append_q_construct(
                        tnc2_to_send, station_config.callsign
                    )
                    aprs_client.send_packet(tnc2_to_send)
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
            _handle_keyboard_commands(command_queue, summary_log_path)

            if (
                not getattr(args, "once", False)
                and time.monotonic() >= next_stats_report
            ):
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                logger.info(
                    "[stats %s] frames=%s aprs_ok=%s aprs_fail=%s",
                    timestamp,
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


def _apply_software_tocall(tnc2_line: str | bytes, tocall: str) -> str | bytes:
    """Return a modified TNC2 line where the DEST is replaced with tocall.

    Only operates on the textual TNC2 form: "SRC>DST[,PATH]:INFO". The
    function preserves any existing path suffix (",...") and the info field.
    Preserves the input type (bytes or str) in the output.
    """
    if not tocall:
        return tnc2_line

    # Work with bytes internally for safety, convert back to original type at end
    if isinstance(tnc2_line, bytes):
        was_bytes = True
        line_bytes = tnc2_line
        tocall_bytes = tocall.encode("ascii")
    else:
        was_bytes = False
        line_bytes = tnc2_line.encode("ascii", errors="replace")
        tocall_bytes = tocall.encode("ascii")

    if b":" not in line_bytes or b">" not in line_bytes:
        return tnc2_line

    header, info = line_bytes.split(b":", 1)
    try:
        src, rest = header.split(b">", 1)
    except ValueError:
        return tnc2_line

    # rest may contain dest[,path]
    if b"," in rest:
        _, path = rest.split(b",", 1)
        new_rest = tocall_bytes + b"," + path
    else:
        new_rest = tocall_bytes

    result = src + b">" + new_rest + b":" + info
    return result if was_bytes else result.decode("ascii", errors="replace")


def _get_source_callsign(tnc2_packet: str | bytes) -> str | None:
    """Extract the source callsign from a TNC2 packet (before the >).

    Handles both str and bytes input, returns str or None.
    """
    if isinstance(tnc2_packet, bytes):
        tnc2_packet = tnc2_packet.decode("ascii", errors="replace")

    tokens = tnc2_packet.split(":")
    if not tokens:
        return None
    header = tokens[0]
    if ">" not in header:
        return None
    return header.split(">", 1)[0]


def _append_q_construct(
    tnc2_line: str | bytes, igate_callsign: str, q_type: str = "qAR"
) -> str | bytes:
    """Append a q construct hop identifying this iGate.

    Frames forwarded to APRS-IS must include a `q` hop describing how they
    reached the Internet (`qAR,<igate>` for heard-via-RF traffic). This helper
    injects the hop unless the frame already carries any q construct.
    """

    was_bytes = isinstance(tnc2_line, (bytes, bytearray))
    if was_bytes:
        line = bytes(tnc2_line)
        if not igate_callsign or b":" not in line or b">" not in line:
            return tnc2_line
        header, info = line.split(b":", 1)
        try:
            src, rest = header.split(b">", 1)
        except ValueError:
            return tnc2_line

        parts = rest.split(b",") if rest else []
        if not parts:
            return tnc2_line

        dest = parts[0]
        path_parts = parts[1:]
        has_q = any(
            p.lower().startswith(b"q") and len(p) >= 3 for p in path_parts
        )
        if has_q:
            return tnc2_line

        new_path = path_parts + [q_type.encode("ascii"), igate_callsign.upper().encode("ascii")]
        combined = b",".join([dest] + new_path)
        return src + b">" + combined + b":" + info
    else:
        line = tnc2_line
        if not igate_callsign or ":" not in line or ">" not in line:
            return tnc2_line
        header, info = line.split(":", 1)
        try:
            src, rest = header.split(">", 1)
        except ValueError:
            return tnc2_line

        parts = rest.split(",") if rest else []
        if not parts:
            return tnc2_line

        dest = parts[0]
        path_parts = parts[1:]
        has_q = any(
            component.lower().startswith("q") and len(component) >= 3
            for component in path_parts
        )
        if has_q:
            return tnc2_line

        new_path = path_parts + [q_type, igate_callsign.upper()]
        combined = ",".join([dest] + new_path)
        return f"{src}>{combined}:{info}"


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


def _display_frame(count: int, port: int, tnc2_line: str | bytes) -> None:
    # Convert bytes to str for display with error handling
    if isinstance(tnc2_line, bytes):
        snippet = tnc2_line.decode("ascii", errors="replace")
    else:
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


def _start_keyboard_listener(
    stop_event: threading.Event, command_queue: "Queue[str]"
) -> threading.Thread | None:
    # If threading.Event has been monkeypatched without a wait method (as in certain tests),
    # avoid starting the keyboard listener to prevent blocking or crashes.
    try:
        test_event = threading.Event()
        if not hasattr(test_event, "wait"):
            return None
    except Exception:
        return None

    if not sys.stdin.isatty():
        return None
    try:
        import select
        import termios
        import tty
    except ImportError:
        return None

    try:
        fd = sys.stdin.fileno()
    except (OSError, ValueError):
        return None

    try:
        old_settings = termios.tcgetattr(fd)
    except termios.error:
        return None

    try:
        tty.setcbreak(fd)
    except termios.error:
        return None

    def worker() -> None:
        try:
            while not stop_event.is_set():
                try:
                    readable, _, _ = select.select([sys.stdin], [], [], 0.1)
                except (OSError, ValueError):
                    break
                if sys.stdin in readable:
                    try:
                        chunk = sys.stdin.read(1)
                    except (OSError, ValueError):
                        break
                    if chunk:
                        command_queue.put(chunk)
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except termios.error:
                pass

    thread = _REAL_THREAD(target=worker, name="neo-rx-keyboard", daemon=True)
    thread.start()
    return thread


def _handle_keyboard_commands(command_queue: "Queue[str]", log_path: Path) -> None:
    while True:
        try:
            command = command_queue.get_nowait()
        except Empty:
            break
        if command.lower() == "s":
            summary = _summarize_recent_activity(log_path)
            # Print summary directly to stdout to avoid duplicating it in the log file.
            print("\n" + summary + "\n", flush=True)


@dataclass
class _StationActivity:
    count: int = 0
    last: datetime = datetime.min.replace(tzinfo=timezone.utc)


def _summarize_recent_activity(
    log_path: Path,
    *,
    window: timedelta = timedelta(hours=24),
    now: datetime | None = None,
) -> str:
    reference_time = now or datetime.now(timezone.utc)
    cutoff = reference_time - window

    if not log_path.exists():
        return "No listener log file available yet; try again after packets arrive."

    stations: dict[str, _StationActivity] = {}
    total_frames = 0

    try:
        with log_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    timestamp_text, message = line.split(" ", 1)
                except ValueError:
                    continue
                try:
                    observed = datetime.strptime(
                        timestamp_text, "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if observed < cutoff:
                    continue
                if not message.startswith("[") or " port=" not in message:
                    continue
                station = _extract_station_from_message(message)
                if station is None:
                    continue
                total_frames += 1
                entry = stations.get(station)
                if entry is None:
                    stations[station] = _StationActivity(count=1, last=observed)
                else:
                    entry.count += 1
                    if observed > entry.last:
                        entry.last = observed
    except OSError as exc:
        return f"Unable to read listener log: {exc}"

    if not stations:
        return "No stations heard in the last 24 hours."

    lines = [
        f"Station activity summary for {reference_time.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"Window: last {window}",
        f"Log file: {log_path}",
        "",
        "── Station activity (last 24h) ──",
        f"Unique stations: {len(stations)} | Frames: {total_frames}",
        "",
    ]

    sorted_items = sorted(
        stations.items(),
        key=lambda item: (-item[1].count, item[0]),
    )

    max_rows = 15
    for station, data in sorted_items[:max_rows]:
        last_text = data.last.strftime("%Y-%m-%d %H:%MZ")
        lines.append(f"{station:<12} {data.count:>5} frames  last {last_text}")

    remaining = len(sorted_items) - max_rows
    if remaining > 0:
        lines.append(f"… plus {remaining} more station(s)")

    return "\n".join(lines)


def _extract_station_from_message(message: str) -> str | None:
    tokens = message.split()
    for token in tokens:
        if ">" in token:
            return token.split(">", 1)[0]
    return None
