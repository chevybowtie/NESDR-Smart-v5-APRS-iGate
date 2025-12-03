"""ADS-B capture orchestration.

This module coordinates ADS-B signal capture and decoding using dump1090
or readsb as the decoder backend. It provides real-time aircraft tracking
using RTL-SDR.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from neo_adsb.adsb.reporter import AdsbExchangeReporter

LOG = logging.getLogger(__name__)

# ADS-B frequency (1090 MHz)
ADSB_FREQUENCY_HZ = 1_090_000_000


@dataclass
class AircraftState:
    """Current state of a tracked aircraft."""

    hex_id: str
    flight: str | None = None
    altitude_ft: int | None = None
    ground_speed_kt: float | None = None
    track_deg: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    vertical_rate_fpm: int | None = None
    squawk: str | None = None
    rssi_db: float | None = None
    seen_s: float = 0.0
    seen_pos_s: float | None = None
    messages: int = 0
    category: str | None = None
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaptureStats:
    """Statistics for the capture session."""

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_messages: int = 0
    total_aircraft: int = 0
    unique_aircraft: int = 0
    max_range_nm: float = 0.0
    max_altitude_ft: int = 0


class Dump1090Client:
    """Client to read aircraft data from dump1090/readsb JSON output.

    This client reads the aircraft.json file produced by dump1090 or readsb
    to obtain current aircraft positions and metadata.
    """

    def __init__(
        self,
        json_path: str | Path = "/run/dump1090-fa/aircraft.json",
        poll_interval_s: float = 1.0,
    ) -> None:
        self.json_path = Path(json_path)
        self.poll_interval_s = poll_interval_s
        self._aircraft: dict[str, AircraftState] = {}
        self._stats = CaptureStats()
        self._lock = threading.Lock()

    def poll(self) -> list[AircraftState]:
        """Poll dump1090 for current aircraft state.

        Returns a list of AircraftState objects for all currently tracked
        aircraft. Updates internal statistics.
        """
        if not self.json_path.exists():
            LOG.debug("dump1090 JSON file not found: %s", self.json_path)
            return []

        try:
            with self.json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            LOG.warning("Failed to read dump1090 JSON: %s", exc)
            return []

        now = datetime.now(timezone.utc)
        aircraft_list = data.get("aircraft", [])
        updated_aircraft: list[AircraftState] = []

        with self._lock:
            for ac_data in aircraft_list:
                hex_id = ac_data.get("hex", "").upper()
                if not hex_id:
                    continue

                # Get or create aircraft state
                if hex_id in self._aircraft:
                    state = self._aircraft[hex_id]
                else:
                    state = AircraftState(hex_id=hex_id, first_seen=now)
                    self._aircraft[hex_id] = state
                    self._stats.unique_aircraft += 1

                # Update state from JSON data
                state.flight = ac_data.get("flight", "").strip() or state.flight
                state.altitude_ft = ac_data.get("alt_geom") or ac_data.get("alt_baro")
                state.ground_speed_kt = ac_data.get("gs")
                state.track_deg = ac_data.get("track")
                state.latitude = ac_data.get("lat")
                state.longitude = ac_data.get("lon")
                state.vertical_rate_fpm = ac_data.get("baro_rate") or ac_data.get(
                    "geom_rate"
                )
                state.squawk = ac_data.get("squawk")
                state.rssi_db = ac_data.get("rssi")
                state.seen_s = ac_data.get("seen", 0.0)
                state.seen_pos_s = ac_data.get("seen_pos")
                state.messages = ac_data.get("messages", 0)
                state.category = ac_data.get("category")
                state.last_seen = now

                # Update stats
                self._stats.total_messages += state.messages
                if state.altitude_ft and state.altitude_ft > self._stats.max_altitude_ft:
                    self._stats.max_altitude_ft = state.altitude_ft

                updated_aircraft.append(state)

            self._stats.total_aircraft = len(aircraft_list)

        return updated_aircraft

    def get_aircraft(self, hex_id: str) -> AircraftState | None:
        """Get state for a specific aircraft by ICAO hex code."""
        with self._lock:
            return self._aircraft.get(hex_id.upper())

    def get_all_aircraft(self) -> list[AircraftState]:
        """Get all currently tracked aircraft."""
        with self._lock:
            return list(self._aircraft.values())

    def get_stats(self) -> CaptureStats:
        """Get current capture statistics."""
        with self._lock:
            return CaptureStats(
                start_time=self._stats.start_time,
                total_messages=self._stats.total_messages,
                total_aircraft=self._stats.total_aircraft,
                unique_aircraft=self._stats.unique_aircraft,
                max_range_nm=self._stats.max_range_nm,
                max_altitude_ft=self._stats.max_altitude_ft,
            )

    def clear_stale(self, max_age_s: float = 60.0) -> int:
        """Remove aircraft not seen for longer than max_age_s.

        Returns the number of aircraft removed.
        """
        now = datetime.now(timezone.utc)
        removed = 0
        with self._lock:
            stale_ids = [
                hex_id
                for hex_id, state in self._aircraft.items()
                if (now - state.last_seen).total_seconds() > max_age_s
            ]
            for hex_id in stale_ids:
                del self._aircraft[hex_id]
                removed += 1
        return removed


class AdsbCapture:
    """Orchestrate ADS-B capture using dump1090/readsb backend.

    This class manages a background thread that monitors dump1090 JSON output
    and optionally reports to ADS-B Exchange.
    """

    def __init__(
        self,
        json_path: str | Path = "/run/dump1090-fa/aircraft.json",
        poll_interval_s: float = 1.0,
        data_dir: Path | None = None,
        publisher: Optional[object] = None,
        reporter: "AdsbExchangeReporter | None" = None,
        station_config: Optional[object] = None,
    ) -> None:
        self._client = Dump1090Client(json_path=json_path, poll_interval_s=poll_interval_s)
        self._poll_interval_s = poll_interval_s
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._data_dir = Path(data_dir) if data_dir is not None else Path("./data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._aircraft_file = self._data_dir / "adsb_aircraft.jsonl"
        self._publisher = publisher
        self._reporter = reporter
        self._station_config = station_config
        self._callbacks: list[Callable[[list[AircraftState]], None]] = []
        self._consecutive_empty = 0

    def add_callback(self, callback: Callable[[list[AircraftState]], None]) -> None:
        """Register a callback to be invoked with aircraft updates."""
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start the ADS-B capture background thread."""
        if self._running:
            LOG.warning("ADS-B capture already started")
            return
        LOG.info("Starting ADS-B capture, reading from: %s", self._client.json_path)
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop, name="adsb_capture", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the ADS-B capture background thread."""
        if not self._running:
            LOG.warning("ADS-B capture not running")
            return
        LOG.info("Stopping ADS-B capture")
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                LOG.warning("ADS-B capture thread did not stop cleanly")

    def is_running(self) -> bool:
        """Return True if the capture thread is running."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def get_client(self) -> Dump1090Client:
        """Return the underlying dump1090 client."""
        return self._client

    def _capture_loop(self) -> None:
        """Main capture loop running in background thread."""
        LOG.info("ADS-B capture loop started")
        stale_check_interval = 30.0
        last_stale_check = time.monotonic()

        while not self._stop_event.is_set():
            try:
                # Debug logging for JSON file state
                if LOG.isEnabledFor(logging.DEBUG):
                    try:
                        stat = self._client.json_path.stat()
                        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                        LOG.debug(
                            "aircraft.json: size=%d bytes, mtime=%s",
                            stat.st_size,
                            mtime,
                        )
                    except FileNotFoundError:
                        LOG.debug("aircraft.json not found at %s", self._client.json_path)

                aircraft = self._client.poll()
                LOG.debug("Decoded %d aircraft records", len(aircraft))

                if aircraft:
                    if self._consecutive_empty > 0:
                        LOG.info(
                            "Aircraft stream resumed after %d empty polls",
                            self._consecutive_empty,
                        )
                    self._consecutive_empty = 0

                    # Log aircraft to file
                    self._log_aircraft(aircraft)

                    # Publish via MQTT if configured
                    if self._publisher:
                        self._publish_aircraft(aircraft)

                    # Notify callbacks
                    for callback in self._callbacks:
                        try:
                            callback(aircraft)
                        except Exception as exc:
                            LOG.warning("Callback error: %s", exc)
                else:
                    self._consecutive_empty += 1
                    if self._consecutive_empty in (5, 15, 30):
                        LOG.warning(
                            "No aircraft detected for %d consecutive polls (%.0fs). "
                            "Check: (1) decoder running: systemctl status readsb dump1090-fa, "
                            "(2) SDR connected: rtl_test -t, "
                            "(3) antenna connected and positioned for line-of-sight",
                            self._consecutive_empty,
                            self._consecutive_empty * self._poll_interval_s,
                        )

                # Periodically clear stale aircraft
                if time.monotonic() - last_stale_check > stale_check_interval:
                    removed = self._client.clear_stale(max_age_s=60.0)
                    if removed > 0:
                        LOG.debug("Cleared %d stale aircraft", removed)
                    last_stale_check = time.monotonic()

            except Exception as exc:
                LOG.exception("Error in ADS-B capture loop: %s", exc)

            self._stop_event.wait(timeout=self._poll_interval_s)

        LOG.info("ADS-B capture loop stopped")

    def _log_aircraft(self, aircraft: list[AircraftState]) -> None:
        """Log aircraft state to JSON-lines file."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._aircraft_file.open("a", encoding="utf-8") as f:
                for ac in aircraft:
                    record = {
                        "timestamp": now,
                        "hex": ac.hex_id,
                        "flight": ac.flight,
                        "altitude_ft": ac.altitude_ft,
                        "ground_speed_kt": ac.ground_speed_kt,
                        "track_deg": ac.track_deg,
                        "latitude": ac.latitude,
                        "longitude": ac.longitude,
                        "squawk": ac.squawk,
                        "rssi_db": ac.rssi_db,
                        "messages": ac.messages,
                    }
                    f.write(json.dumps(record) + "\n")
        except OSError as exc:
            LOG.warning("Failed to log aircraft: %s", exc)

    def _publish_aircraft(self, aircraft: list[AircraftState]) -> None:
        """Publish aircraft state via MQTT."""
        if not self._publisher:
            return
        try:
            topic = getattr(self._publisher, "topic", "neo_rx/adsb/aircraft")
            count = 0
            for ac in aircraft:
                payload = json.dumps(
                    {
                        "hex": ac.hex_id,
                        "flight": ac.flight,
                        "altitude_ft": ac.altitude_ft,
                        "latitude": ac.latitude,
                        "longitude": ac.longitude,
                    }
                )
                self._publisher.publish(topic, payload)
                count += 1
            if logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
                LOG.debug("Published %d aircraft to MQTT topic %s", count, topic)
        except Exception as exc:
            LOG.warning("Failed to publish aircraft: %s", exc)
