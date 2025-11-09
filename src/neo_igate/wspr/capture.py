"""Capture orchestration for WSPR (skeleton).

This module will coordinate SDR captures, scheduling, and hand-off to the
decoder. It currently provides a minimal stub useful for wiring into the CLI.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Iterable, Optional

LOG = logging.getLogger(__name__)


CaptureFunc = Callable[[int, int], Iterable[bytes | str]]


class WsprCapture:
    """Orchestrate WSPR captures across bands.

    The capture pipeline is intentionally synchronous and testable: callers
    provide a `capture_fn` that when called with `(band_hz, duration_s)`
    returns an iterable of bytes/strings representing decoder output or
    captured audio/text. This allows unit tests to inject fixtures rather
    than rely on real SDR hardware.

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
        self.bands_hz = bands_hz or [14_080_000]
        self.capture_duration_s = capture_duration_s
        self._running = False
        self._data_dir = Path(data_dir) if data_dir is not None else Path("./data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._spots_file = self._data_dir / "wspr_spots.jsonl"
        self._publisher = publisher

    def start(self) -> None:
        LOG.info("WSPR capture started")
        self._running = True

    def stop(self) -> None:
        LOG.info("WSPR capture stopped")
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def run_capture_cycle(self, capture_fn: CaptureFunc) -> list[dict]:
        """Run a single capture for each configured band using `capture_fn`.

        For each band, call `capture_fn(band_hz, duration_s)`, feed the
        resulting lines to the decoder, append spots to the local JSON-lines
        file, and publish via the configured publisher (if present).

        Returns the list of parsed spot dicts from this cycle.
        """
        from .decoder import WsprDecoder

        if not self._running:
            raise RuntimeError("Capture not started")

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
                        self._publisher.publish(topic, spot)
                    except Exception:
                        LOG.exception("Publisher failed to publish spot; continuing")

        return all_spots
