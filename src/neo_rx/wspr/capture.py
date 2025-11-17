"""Capture orchestration for WSPR.

This module coordinates SDR captures, scheduling, and hand-off to the
decoder. It provides real-time multi-band WSPR capture using RTL-SDR.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, TYPE_CHECKING

from neo_rx.config import StationConfig

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from neo_rx.wspr.uploader import WsprUploader

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
        capture_duration_s: int = 119,  # 119 seconds to allow processing time before next 2-min window
        data_dir: Path | None = None,
        publisher: Optional[object] = None,
        upconverter_enabled: bool = False,
        upconverter_offset_hz: int | None = None,
        keep_temp: bool = False,
        station_config: StationConfig | None = None,
        uploader: "WsprUploader | None" = None,
    ) -> None:
        # Default to primary WSPR bands (Hz)
        self.bands_hz = bands_hz or [
            3_594_000,   # 80m
            7_038_600,   # 40m
            14_095_600,  # 20m
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
        self._upconverter_enabled = upconverter_enabled
        self._upconverter_offset_hz = upconverter_offset_hz or 125_000_000  # Default 125MHz
        # When True, preserve wsprd temp files for debugging
        self._keep_temp = bool(keep_temp)
        self._station_config = station_config
        self._uploader = uploader

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
        from neo_rx._compat import prepare_rtlsdr

        # Prepare RTL-SDR with compatibility patches
        prepare_rtlsdr()

        try:
            from rtlsdr import RtlSdrAio as RtlSdr
        except ImportError:
            try:
                from rtlsdr import RtlSdr
            except ImportError as exc:
                LOG.error("RTL-SDR library not available: %s", exc)
                self._running = False
                return

        sdr = None
        try:
            # Check for devices
            try:
                device_count = RtlSdr.get_device_count()  # type: ignore[attr-defined]
            except AttributeError:
                # Some versions don't have get_device_count, assume available
                device_count = 1
            if device_count == 0:
                LOG.error("No RTL-SDR devices found")
                self._running = False
                return

            sdr = RtlSdr()  # type: ignore[operator]
            LOG.info("RTL-SDR initialized for WSPR capture")
            LOG.info("Note: '[R82XX] PLL not locked!' messages during tuning are normal and don't indicate errors")

            # Check system time accuracy - critical for WSPR synchronization
            import datetime
            now = datetime.datetime.now()
            if now.year < 2024:
                LOG.warning("System time appears to be incorrect (year %d). WSPR synchronization requires accurate system time within seconds. Please configure NTP (e.g., 'sudo apt install ntp' and 'sudo systemctl enable ntp').", now.year)
            else:
                LOG.info("System time appears reasonable. For optimal WSPR reception, ensure NTP synchronization: 'timedatectl status' should show 'NTP synchronized: yes'")

            decoder = WsprDecoder()

            # Wait for next even minute to synchronize with WSPR schedule
            now = time.time()
            seconds_since_epoch = int(now)
            current_minute = (seconds_since_epoch // 60) % 60
            seconds_into_minute = seconds_since_epoch % 60
            
            if current_minute % 2 == 0:
                # Already at even minute, wait until next even minute
                wait_seconds = 120 - seconds_into_minute
            else:
                # At odd minute, wait until next even minute
                wait_seconds = (120 - seconds_into_minute) % 120
            
            if wait_seconds > 0:
                LOG.info("Waiting %d seconds to synchronize with WSPR schedule (next even minute)", wait_seconds)
                # Countdown with updates every second
                for remaining in range(wait_seconds, 0, -1):
                    if self._stop_event.wait(1.0):  # Wait 1 second, check for stop
                        return
                    if remaining <= 10 or remaining % 10 == 0:  # Log every 10 seconds, or last 10
                        LOG.info("WSPR sync: %d seconds remaining", remaining)
                LOG.info("WSPR synchronization complete - starting capture")

            while not self._stop_event.is_set():
                for band_hz in self.bands_hz:
                    if self._stop_event.is_set():
                        break

                    LOG.info("Tuning to band %s Hz for %s s", band_hz, self.capture_duration_s)
                    try:
                        # Apply upconverter offset if enabled
                        if self._upconverter_enabled and self._upconverter_offset_hz:
                            actual_freq = band_hz + self._upconverter_offset_hz
                            LOG.info("RTL-SDR tuning to %.3f MHz (HF: %.3f MHz + %d MHz upconverter offset)", 
                                   actual_freq / 1e6, band_hz / 1e6, self._upconverter_offset_hz // 1_000_000)
                        else:
                            actual_freq = band_hz
                            LOG.info("RTL-SDR tuning to %.3f MHz (no upconverter)", actual_freq / 1e6)
                        sdr.set_center_freq(actual_freq)  # type: ignore[attr-defined]
                        # Allow PLL to settle after frequency change
                        time.sleep(0.1)  # 100ms delay for tuner stabilization
                        sdr.set_sample_rate(1_200_000)  # Standard for WSPR
                        sdr.set_gain(35)  # Set gain to 35dB (matches SDR++ settings of 20-35dB range)
                        LOG.info("RTL-SDR configured: sample rate 1.2 MHz, gain 35dB")
                        # Capture IQ samples
                        iq_data = b""
                        start_time = time.time()
                        last_progress = start_time
                        iterations = 0
                        # Increase chunk size to improve throughput; some rtlsdr bindings
                        # are more efficient with larger read sizes.
                        chunk_size = 16384

                        # Prefer async/callback-based capture if supported by the binding.
                        use_async = hasattr(sdr, 'read_samples_async')
                        if use_async:
                            LOG.info("Using async capture via read_samples_async")
                            buf = bytearray()

                            def _async_cb(samples, rtlsdr_obj=None):
                                # samples is typically a numpy array of complex64
                                try:
                                    for sample in samples:
                                        buf.extend(int(sample.real * 32767).to_bytes(2, 'little', signed=True))
                                        buf.extend(int(sample.imag * 32767).to_bytes(2, 'little', signed=True))
                                    # Do not call cancel_read_async() from the callback; the
                                    # main thread will stop the async read when the duration
                                    # has elapsed. Calling cancel from the callback can race
                                    # with librtlsdr internals and cause crashes.
                                except Exception:
                                    LOG.exception("Error in async capture callback")

                            import threading as _threading

                            reader_thread = _threading.Thread(target=lambda: sdr.read_samples_async(_async_cb, chunk_size), daemon=True)
                            reader_thread.start()

                            # Wait until duration elapsed or stop requested
                            while time.time() - start_time < self.capture_duration_s and not self._stop_event.is_set():
                                time.sleep(0.1)

                            # Ensure async read stopped. Call cancel_read_async from the
                            # main thread and wait (up to a few seconds) for the reader
                            # thread to exit cleanly. This avoids races that can cause
                            # segmentation faults in librtlsdr when cancel is invoked
                            # from the callback thread.
                            try:
                                sdr.cancel_read_async()
                            except Exception:
                                LOG.debug("sdr.cancel_read_async() raised an exception during shutdown")

                            # Wait for the reader thread to exit (give it up to 5s).
                            timeout = 5.0
                            waited = 0.0
                            interval = 0.05
                            while reader_thread.is_alive() and waited < timeout:
                                time.sleep(interval)
                                waited += interval

                            if reader_thread.is_alive():
                                LOG.warning("Async reader thread did not exit within %.1fs", timeout)

                            iq_data = bytes(buf)
                        else:
                            # Fallback synchronous capture (existing approach)
                            while time.time() - start_time < self.capture_duration_s and not self._stop_event.is_set():
                                samples = sdr.read_samples(chunk_size)  # Read in larger chunks
                                # Convert complex samples to bytes (IQ as int16)
                                iq_bytes = b"".join(
                                    int(sample.real * 32767).to_bytes(2, 'little', signed=True) +
                                    int(sample.imag * 32767).to_bytes(2, 'little', signed=True)
                                    for sample in samples
                                )
                                iq_data += iq_bytes

                                iterations += 1
                                # Periodically log progress (every ~5 seconds)
                                now = time.time()
                                if now - last_progress >= 5.0:
                                    try:
                                        total_samples = len(iq_data) // 4
                                        elapsed = now - start_time
                                        LOG.info("WSPR capture progress: %d complex samples in %.1fs (%.1f sps)", total_samples, elapsed, total_samples / max(1.0, elapsed))
                                    except Exception:
                                        LOG.debug("Failed to compute capture progress")
                                    last_progress = now

                        # Decode using wsprd
                        if iq_data:
                            # Log capture diagnostics: sample rate reported by driver and written data size
                            try:
                                actual_sr = getattr(sdr, 'get_sample_rate', None)
                                if callable(actual_sr):
                                    reported_sr = actual_sr()
                                else:
                                    # Some bindings expose property instead
                                    reported_sr = getattr(sdr, 'sample_rate', None)
                                if reported_sr:
                                    LOG.info("RTL-SDR reported sample rate: %s", reported_sr)
                            except Exception:
                                LOG.debug("Could not read sample rate from SDR object")
                            try:
                                total_samples = len(iq_data) // 4
                                inferred_duration = total_samples / float(1_200_000)
                                LOG.info("Captured %d complex samples (%.2f seconds at 1.2e6 sps assumed)", total_samples, inferred_duration)
                            except Exception:
                                LOG.debug("Failed to compute captured sample count/duration")
                            for spot in decoder.run_wsprd_subprocess(iq_data, band_hz, keep_temp=self._keep_temp):
                                self._handle_spot(spot, band_hz)

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

    def _handle_spot(self, spot: dict, band_hz: int) -> dict:
        """Handle a decoded spot: enrich, persist, publish, and enqueue if enabled."""
        enriched, missing_for_queue = self._enrich_spot(spot, band_hz)
        self._persist_spot(enriched)
        self._publish_spot(enriched)
        self._maybe_enqueue_spot(enriched, missing_for_queue)
        return enriched

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
                enriched = self._handle_spot(spot, band)
                all_spots.append(enriched)

        return all_spots

    def _persist_spot(self, spot: dict) -> None:
        try:
            with self._spots_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(spot, default=str) + "\n")
        except Exception:
            LOG.exception("Failed to write spot to file: %s", self._spots_file)

    def _publish_spot(self, spot: dict) -> None:
        if self._publisher is None:
            return
        try:
            topic = getattr(self._publisher, "topic", "neo_rx/wspr/spots")
            self._publisher.publish(topic, spot)  # type: ignore[attr-defined]
        except Exception:
            LOG.exception("Publisher failed to publish spot; continuing")

    def _maybe_enqueue_spot(self, spot: dict, missing_fields: list[str]) -> None:
        if self._uploader is None:
            return
        lacking = sorted({field for field in missing_fields})
        if lacking:
            LOG.warning(
                "Skipping WSPR uploader enqueue due to missing metadata: %s",
                ", ".join(lacking),
            )
            return
        try:
            self._uploader.enqueue_spot(spot)
        except Exception:
            LOG.exception("Failed to enqueue spot for WSPR uploader; queue unchanged")

    def _enrich_spot(self, spot: dict, band_hz: int) -> tuple[dict, list[str]]:
        enriched = dict(spot)
        missing: list[str] = []

        enriched["dial_freq_hz"] = band_hz

        slot_start = _compute_slot_start(enriched.get("timestamp"))
        if slot_start is None:
            missing.append("slot_start_utc")
        else:
            enriched["slot_start_utc"] = slot_start

        if self._station_config is not None:
            reporter_callsign = self._station_config.callsign
            if reporter_callsign:
                enriched["reporter_callsign"] = reporter_callsign
            else:
                missing.append("reporter_callsign")

            reporter_grid = self._station_config.wspr_grid
            if reporter_grid:
                enriched["reporter_grid"] = reporter_grid
            else:
                missing.append("reporter_grid")

            reporter_power = self._station_config.wspr_power_dbm
            if reporter_power is not None:
                enriched["reporter_power_dbm"] = reporter_power
            else:
                missing.append("reporter_power_dbm")
        else:
            missing.extend(["reporter_callsign", "reporter_grid", "reporter_power_dbm"])

        return enriched, missing


def _compute_slot_start(timestamp: str | None) -> str | None:
    if not timestamp:
        return None
    try:
        normalized = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    slot_minute = (dt.minute // 2) * 2
    dt = dt.replace(minute=slot_minute, second=0, microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")
