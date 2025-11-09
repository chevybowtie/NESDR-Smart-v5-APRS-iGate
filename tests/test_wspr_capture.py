import json
from pathlib import Path

from neo_igate.wspr.capture import WsprCapture


def fake_capture_fn(band_hz: int, duration_s: int):
    # Return lines that the decoder expects (reuse fixture format)
    return [
        "2025-11-08 12:34:00 14080000 K1ABC FN42 -12 0.5\n",
        "2025-11-08 12:36:00 14097000 G4XYZ IO91 -9\n",
    ]


def test_run_capture_cycle(tmp_path: Path):
    data_dir = tmp_path / "data"
    cap = WsprCapture(bands_hz=[14080000], capture_duration_s=10, data_dir=data_dir)
    cap.start()
    spots = cap.run_capture_cycle(fake_capture_fn)
    cap.stop()

    assert len(spots) == 2

    spots_file = data_dir / "wspr_spots.jsonl"
    assert spots_file.exists()
    lines = spots_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["call"] == "K1ABC"
