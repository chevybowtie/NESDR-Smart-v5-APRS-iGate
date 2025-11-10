"""Capture orchestration for WSPR.

This module coordinates SDR captures, scheduling, and hand-off to the
decoder. It provides real-time multi-band WSPR capture using RTL-SDR.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

LOG = logging.getLogger(__name__)


CaptureFunc = Callable[[int, int], Iterable[bytes | str]]


class WsprCapture:
    """Orchestrate WSPR captures across bands using RTL-SDR.

    This class manages a background thread that cycles through configured
    WSPR bands, captures IQ samples from the RTL-SDR, decodes them using
    `wsprd`, and publishes spots.

    When a `publisher` is provided, parsed spots will be published via
    `publisher.publish(topic, payload)`. Spots are also appended to a
    JSON-lines file under the provided `data_dir`.
    """

    def __init__(
        self,
        bands_hz: list[int] | None = None,
        capture_duration_s: int = 120,
        data_dir: Path | None = None,
        publisher: Optional[object] = None,
    ) -> None:
        # Default to primary WSPR bands (Hz)
        self.bands_hz = bands_hz or [
            3_594_000,   # 80m
            7_038_600,   # 40m
            10_140_200,  # 30m
            28_124_600,  # 10m
        ]
        self.capture_duration_s = capture_duration_s
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._data_dir = Path(data_dir) if data_dir is not None else Path("./data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._spots_file = self._data_dir / "wspr_spots.jsonl"
        self._publisher = publisher

    def start(self) -> None:
        if self._running:
            LOG.warning("WSPR capture already started")
            return
        LOG.info("Starting WSPR capture with bands: %s", self.bands_hz)
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, name="wspr_capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            LOG.warning("WSPR capture not running")
            return
        LOG.info("Stopping WSPR capture")
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                LOG.warning("WSPR capture thread did not stop cleanly")

    def is_running(self) -> bool:
        return self._running

    def _capture_loop(self) -> None:
        """Background capture loop: cycle through bands, capture, decode, publish."""
        from .decoder import WsprDecoder
        from neo_igate._compat import prepare_rtlsdr

        # Prepare RTL-SDR with compatibility patches
        prepare_rtlsdr()

        try:
            from rtlsdr import RtlSdr
        except ImportError as exc:
            LOG.error("RTL-SDR library not available: %s", exc)
            self._running = False
            return

        sdr = None
        try:
            # Check for devices
            device_count = RtlSdr.get_device_count()  # type: ignore[attr-defined]
            if device_count == 0:
                LOG.error("No RTL-SDR devices found")
                self._running = False
                return

            sdr = RtlSdr()  # type: ignore[operator]
            LOG.info("RTL-SDR initialized for WSPR capture")

            decoder = WsprDecoder()

            while not self._stop_event.is_set():
                for band_hz in self.bands_hz:
                    if self._stop_event.is_set():
                        break

                    LOG.info("Tuning to band %s Hz for %s s", band_hz, self.capture_duration_s)
                    try:
                        sdr.set_center_freq(band_hz)  # type: ignore[attr-defined]
                        sdr.set_sample_rate(1_200_000)  # Standard for WSPR
                        # Capture IQ samples
                        iq_data = b""
                        start_time = time.time()
                        while time.time() - start_time < self.capture_duration_s and not self._stop_event.is_set():
                            samples = sdr.read_samples(1024)  # Read in chunks
                            # Convert complex samples to bytes (IQ as int16)
                            iq_bytes = b"".join(
                                int(sample.real * 32767).to_bytes(2, 'little', signed=True) +
                                int(sample.imag * 32767).to_bytes(2, 'little', signed=True)
                                for sample in samples
                            )
                            iq_data += iq_bytes

                        # Decode using wsprd
                        if iq_data:
                            for spot in decoder.run_wsprd_subprocess(iq_data, band_hz):
                                self._handle_spot(spot)

                    except Exception as exc:
                        LOG.error("Error capturing band %s: %s", band_hz, exc)
                        continue

        except Exception as exc:
            LOG.error("WSPR capture loop failed: %s", exc)
        finally:
            if sdr:
                try:
                    sdr.close()
                except Exception:
                    pass
            self._running = False

    def _handle_spot(self, spot: dict) -> None:
        """Handle a decoded spot: log, save to file, publish."""
        # append to JSON-lines file
        try:
            with self._spots_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(spot, default=str) + "\n")
        except Exception:
            LOG.exception("Failed to write spot to file: %s", self._spots_file)

        # publish if available
        if self._publisher is not None:
            try:
                topic = getattr(self._publisher, "topic", "neo_igate/wspr/spots")
                self._publisher.publish(topic, spot)  # type: ignore[attr-defined]
            except Exception:
                LOG.exception("Publisher failed to publish spot; continuing")

    def run_capture_cycle(self, capture_fn: CaptureFunc) -> list[dict]:
        """Run a single capture for each configured band using `capture_fn`.

        For each band, call `capture_fn(band_hz, duration_s)`, feed the
        resulting lines to the decoder, append spots to the local JSON-lines
        file, and publish via the configured publisher (if present).

        Returns the list of parsed spot dicts from this cycle.
        """
        from .decoder import WsprDecoder

        decoder = WsprDecoder()
        all_spots: list[dict] = []

        for band in self.bands_hz:
            LOG.info("Capturing band %s for %ss", band, self.capture_duration_s)
            try:
                lines = capture_fn(band, self.capture_duration_s)
            except Exception:
                LOG.exception("capture_fn failed for band %s", band)
                continue

            for spot in decoder.decode_stream(lines):
                all_spots.append(spot)
                self._handle_spot(spot)

        return all_spots
