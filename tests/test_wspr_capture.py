import json
from types import SimpleNamespace

import pytest


def test_run_capture_cycle_persist_publish_enqueue(tmp_path):
    from neo_wspr.wspr.capture import WsprCapture

    # Fake dependencies
    published = []

    class Pub:
        topic = "neo_rx/wspr/spots"

        def publish(self, topic, payload):
            published.append((topic, payload))

    enqueued = []

    class Upl:
        def enqueue_spot(self, spot):
            enqueued.append(spot)

    station_config = SimpleNamespace(
        callsign="TESTCALL", wspr_grid="FN20", wspr_power_dbm=5
    )

    data_dir = tmp_path / "data"
    capture = WsprCapture(
        bands_hz=[14095200],
        capture_duration_s=1,
        data_dir=data_dir,
        publisher=Pub(),
        station_config=station_config,
        uploader=Upl(),
    )

    # Provide a single well-formed wsprd-like output line
    def capture_fn(band, duration):
        return [
            "2025-12-11 12:02:00 14095200 TESTCALL FN20 12 +0.1\n",
        ]

    results = capture.run_capture_cycle(capture_fn)

    # One spot returned
    assert isinstance(results, list) and len(results) == 1
    spot = results[0]

    # Publisher was invoked with expected topic and payload content
    assert published, "publisher.publish was not called"
    topic, payload = published[0]
    assert topic == "neo_rx/wspr/spots"
    assert payload["call"] == "TESTCALL"
    assert payload["grid"] == "FN20"
    assert payload["dial_freq_hz"] == 14095200

    # Spot was persisted to disk as JSON lines
    spots_file = data_dir / "wspr_spots.jsonl"
    assert spots_file.exists()
    with spots_file.open("r", encoding="utf-8") as fh:
        lines = [json.loads(l) for l in fh]
    assert lines and lines[0]["call"] == "TESTCALL"

    # Uploader should have enqueued the spot because station_config provided
    assert enqueued and enqueued[0]["call"] == "TESTCALL"


def test_compute_slot_start_variants():
    from neo_wspr.wspr.capture import _compute_slot_start

    # None input -> None
    assert _compute_slot_start(None) is None

    # Malformed input -> None
    assert _compute_slot_start("not-a-timestamp") is None

    # Time that falls into minute 3 should map to minute 2 (even slot)
    ts = "2025-12-11T12:03:15Z"
    slot = _compute_slot_start(ts)
    assert slot.endswith("T12:02:00Z")

    # Naive timestamp without explicit Z should be parsed and returned as Z
    ts2 = "2025-12-11 12:04:59"
    slot2 = _compute_slot_start(ts2)
    # minute 4 -> slot 4
    assert slot2.endswith("T12:04:00Z")
import json
from pathlib import Path

from neo_core.config import StationConfig
from neo_wspr.wspr.capture import WsprCapture


def fake_capture_fn(band_hz: int, duration_s: int):
    # Return lines that the decoder expects (reuse fixture format)
    return [
        "2025-11-08 12:34:00 14080000 K1ABC FN42 -12 0.5\n",
        "2025-11-08 12:36:00 14097000 G4XYZ IO91 -9\n",
    ]


class DummyUploader:
    def __init__(self) -> None:
        self.enqueued: list[dict] = []

    def enqueue_spot(self, spot: dict) -> None:
        self.enqueued.append(spot)


def _station_cfg(**overrides):
    base = {
        "callsign": "N0CALL-10",
        "passcode": "12345",
        "wspr_grid": "EM12ab",
        "wspr_power_dbm": 33,
    }
    base.update(overrides)
    return StationConfig(**base)


def test_run_capture_cycle_enriches_spots(tmp_path: Path):
    data_dir = tmp_path / "data"
    cfg = _station_cfg()
    cap = WsprCapture(
        bands_hz=[14080000],
        capture_duration_s=10,
        data_dir=data_dir,
        station_config=cfg,
    )
    cap.start()
    spots = cap.run_capture_cycle(fake_capture_fn)
    cap.stop()

    assert len(spots) == 2
    first = spots[0]
    assert first["call"] == "K1ABC"
    assert first["dial_freq_hz"] == 14080000
    assert first["slot_start_utc"] == "2025-11-08T12:34:00Z"
    assert first["reporter_callsign"] == cfg.callsign
    assert first["reporter_grid"] == cfg.wspr_grid
    assert first["reporter_power_dbm"] == cfg.wspr_power_dbm

    spots_file = data_dir / "wspr_spots.jsonl"
    assert spots_file.exists()
    lines = spots_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first_disk = json.loads(lines[0])
    assert first_disk["slot_start_utc"] == "2025-11-08T12:34:00Z"


def test_capture_enqueues_when_metadata_present(tmp_path: Path):
    data_dir = tmp_path / "data"
    uploader = DummyUploader()
    cfg = _station_cfg()
    cap = WsprCapture(
        bands_hz=[14080000],
        capture_duration_s=10,
        data_dir=data_dir,
        station_config=cfg,
        uploader=uploader,
    )
    cap.start()
    cap.run_capture_cycle(fake_capture_fn)
    cap.stop()

    assert len(uploader.enqueued) == 2
    assert uploader.enqueued[0]["reporter_grid"] == "EM12ab"


def test_capture_skips_enqueue_without_grid(tmp_path: Path):
    data_dir = tmp_path / "data"
    uploader = DummyUploader()
    cfg = _station_cfg(wspr_grid=None)
    cap = WsprCapture(
        bands_hz=[14080000],
        capture_duration_s=10,
        data_dir=data_dir,
        station_config=cfg,
        uploader=uploader,
    )
    cap.start()
    cap.run_capture_cycle(fake_capture_fn)
    cap.stop()

    assert uploader.enqueued == []
