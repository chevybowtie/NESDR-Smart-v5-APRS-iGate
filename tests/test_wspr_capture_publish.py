from pathlib import Path

from neo_rx.wspr.capture import WsprCapture


class MockPublisher:
    def __init__(self):
        self.publishes = []
        self.topic = "neo_rx/wspr/spots"

    def connect(self):
        pass

    def publish(self, topic, payload):
        self.publishes.append((topic, payload))

    def close(self):
        pass


def fake_capture_fn(band_hz: int, duration_s: int):
    return [
        "2025-11-08 12:34:00 14080000 K1ABC FN42 -12 0.5\n",
    ]


def test_capture_publishes(tmp_path: Path):
    publisher = MockPublisher()
    cap = WsprCapture(bands_hz=[14080000], capture_duration_s=10, data_dir=tmp_path, publisher=publisher)
    cap.start()
    spots = cap.run_capture_cycle(fake_capture_fn)
    cap.stop()

    assert len(spots) == 1
    assert len(publisher.publishes) == 1
    topic, payload = publisher.publishes[0]
    assert topic == "neo_rx/wspr/spots"
    assert payload["call"] == "K1ABC"
