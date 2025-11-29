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
