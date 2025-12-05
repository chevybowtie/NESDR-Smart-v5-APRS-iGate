"""POCSAG pager capture and decoding.

This module coordinates POCSAG signal capture and decoding using multimon-ng
as the decoder backend. It provides real-time pager message reception
using RTL-SDR.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from neo_core.radio.capture import AudioCaptureError, RtlFmAudioCapture, RtlFmConfig

LOG = logging.getLogger(__name__)

# Default POCSAG frequency (152.840 MHz - common US pager frequency)
DEFAULT_POCSAG_FREQUENCY_HZ = 152_840_000


@dataclass
class PocsagMessage:
    """A decoded POCSAG message."""

    address: int
    function: int
    message_type: str  # 'numeric' or 'alpha'
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rssi_db: Optional[float] = None


@dataclass
class CaptureStats:
    """Statistics for the capture session."""

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_messages: int = 0
    unique_addresses: int = 0


class PocsagCapture:
    """Orchestrate POCSAG capture using multimon-ng backend.

    This class manages a background thread that captures audio via RTL-SDR,
    pipes it to multimon-ng for decoding, and parses the output.
    """

    def __init__(
        self,
        frequency_hz: int = DEFAULT_POCSAG_FREQUENCY_HZ,
        sample_rate: int = 22_050,
        gain: Optional[float] = None,
        ppm: int = 0,
        device_index: int = 0,
        data_dir: Optional[Path] = None,
        publisher: Optional[object] = None,
    ) -> None:
        self._frequency_hz = frequency_hz
        self._sample_rate = sample_rate
        self._gain = gain
        self._ppm = ppm
        self._device_index = device_index
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._data_dir = Path(data_dir) if data_dir is not None else Path("./data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._messages_file = self._data_dir / "pocsag_messages.jsonl"
        self._publisher = publisher
        self._callbacks: list[Callable[[PocsagMessage], None]] = []
        self._stats = CaptureStats()
        self._seen_addresses: set[int] = set()

    def add_callback(self, callback: Callable[[PocsagMessage], None]) -> None:
        """Register a callback to be invoked with message updates."""
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start the POCSAG capture background thread."""
        if self._running:
            LOG.warning("POCSAG capture already started")
            return
        LOG.info("Starting POCSAG capture at %d Hz", self._frequency_hz)
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop, name="pocsag_capture", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the POCSAG capture background thread."""
        if not self._running:
            LOG.warning("POCSAG capture not running")
            return
        LOG.info("Stopping POCSAG capture")
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                LOG.warning("POCSAG capture thread did not stop cleanly")

    def is_running(self) -> bool:
        """Return True if the capture thread is running."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def get_stats(self) -> CaptureStats:
        """Get current capture statistics."""
        return CaptureStats(
            start_time=self._stats.start_time,
            total_messages=self._stats.total_messages,
            unique_addresses=len(self._seen_addresses),
        )

    def _capture_loop(self) -> None:
        """Main capture loop running in background thread."""
        LOG.info("POCSAG capture loop started")

        rtl_config = RtlFmConfig(
            frequency_hz=self._frequency_hz,
            sample_rate=self._sample_rate,
            gain=self._gain,
            ppm=self._ppm,
            device_index=self._device_index,
        )

        capture = RtlFmAudioCapture(rtl_config)
        multimon_proc: Optional[subprocess.Popen[bytes]] = None

        try:
            LOG.info("Starting RTL-SDR capture...")
            capture.start()

            # Start multimon-ng process
            multimon_cmd = [
                "multimon-ng",
                "-a", "POCSAG512",
                "-f", "alpha",
                "-t", "raw",
                "-",
            ]
            multimon_proc = subprocess.Popen(
                multimon_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            LOG.info("Multimon-ng started (PID %s)", multimon_proc.pid)

            audio_thread = threading.Thread(
                target=self._pump_audio, args=(capture, multimon_proc), daemon=True
            )
            audio_thread.start()

            # Read multimon output
            if multimon_proc.stdout:
                for line_bytes in iter(multimon_proc.stdout.readline, b""):
                    if self._stop_event.is_set():
                        break
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    message = self._parse_multimon_line(line)
                    if message:
                        self._handle_message(message)

        except Exception as exc:
            LOG.exception("Error in POCSAG capture loop: %s", exc)
        finally:
            capture.stop()
            if multimon_proc:
                if multimon_proc.stdin:
                    try:
                        multimon_proc.stdin.close()
                    except OSError:
                        pass
                multimon_proc.terminate()
                try:
                    multimon_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    multimon_proc.kill()

        LOG.info("POCSAG capture loop stopped")

    def _pump_audio(self, capture: RtlFmAudioCapture, proc: subprocess.Popen[bytes]) -> None:
        """Pump audio from capture to multimon process."""
        try:
            while not self._stop_event.is_set() and proc.poll() is None:
                chunk = capture.read(4096)
                if not chunk:
                    continue
                if proc.stdin:
                    try:
                        proc.stdin.write(chunk)
                        proc.stdin.flush()
                    except BrokenPipeError:
                        break
        except Exception as exc:
            LOG.exception("Audio pump error: %s", exc)

    def _parse_multimon_line(self, line: str) -> Optional[PocsagMessage]:
        """Parse a line from multimon-ng output."""
        # Example: POCSAG512: Address: 1234567  Function: 0  Alpha: Hello World
        if not line.startswith("POCSAG512:"):
            return None

        parts = line.split()
        if len(parts) < 6:
            return None

        try:
            address_idx = parts.index("Address:")
            function_idx = parts.index("Function:")
            message_type = "alpha" if "Alpha:" in parts else "numeric"
            message_idx = parts.index("Alpha:" if message_type == "alpha" else "Numeric:")

            address = int(parts[address_idx + 1])
            function = int(parts[function_idx + 1])
            message = " ".join(parts[message_idx + 1:])

            return PocsagMessage(
                address=address,
                function=function,
                message_type=message_type,
                message=message,
            )
        except (ValueError, IndexError):
            LOG.debug("Failed to parse multimon line: %s", line)
            return None

    def _handle_message(self, message: PocsagMessage) -> None:
        """Handle a decoded message."""
        LOG.info(
            "POCSAG: Address %d, Function %d, %s: %s",
            message.address,
            message.function,
            message.message_type,
            message.message,
        )

        self._stats.total_messages += 1
        self._seen_addresses.add(message.address)

        # Log to file
        self._log_message(message)

        # Publish via MQTT if configured
        if self._publisher:
            self._publish_message(message)

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(message)
            except Exception as exc:
                LOG.warning("Callback error: %s", exc)

    def _log_message(self, message: PocsagMessage) -> None:
        """Log message to JSON-lines file."""
        import json
        try:
            record = {
                "timestamp": message.timestamp.isoformat(),
                "address": message.address,
                "function": message.function,
                "message_type": message.message_type,
                "message": message.message,
                "rssi_db": message.rssi_db,
            }
            with self._messages_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as exc:
            LOG.warning("Failed to log message: %s", exc)

    def _publish_message(self, message: PocsagMessage) -> None:
        """Publish message via MQTT."""
        if not self._publisher:
            return
        try:
            topic = getattr(self._publisher, "topic", "neo_rx/pocsag/messages")
            payload = {
                "address": message.address,
                "function": message.function,
                "message_type": message.message_type,
                "message": message.message,
                "timestamp": message.timestamp.isoformat(),
            }
            self._publisher.publish(topic, payload)
        except Exception as exc:
            LOG.warning("Failed to publish message: %s", exc)