import json
import sys
import time
from pathlib import Path

import rtlsdr as rtlsdr_module

from neo_core.config import StationConfig
from neo_wspr.wspr import decoder as decoder_module
from neo_wspr.wspr.capture import SPOTS_LOG_RETENTION_ENV_VAR, WsprCapture


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


class _SyncFakeRtlSdr:
    """Fake RTL-SDR exposing only the synchronous read_samples() API.

    _capture_loop() prefers read_samples_async() when the binding offers it,
    so deliberately not defining that method here forces the synchronous
    fallback path -- the code path most likely to be affected by a pyrtlsdr
    API change.
    """

    created: list["_SyncFakeRtlSdr"] = []

    def __init__(self) -> None:
        _SyncFakeRtlSdr.created.append(self)
        self.center_freq: int | None = None
        self.sample_rate: int | None = None
        self.gain: int | None = None
        self.closed = False
        self.read_calls = 0

    @staticmethod
    def get_device_count() -> int:
        return 1

    def set_center_freq(self, freq: int) -> None:
        self.center_freq = freq

    def set_sample_rate(self, rate: int) -> None:
        self.sample_rate = rate

    def set_gain(self, gain: int) -> None:
        self.gain = gain

    def read_samples(self, num_samples: int):
        self.read_calls += 1
        return [complex(0.2, -0.1) for _ in range(8)]

    def close(self) -> None:
        self.closed = True


def _patch_rtlsdr_classes(monkeypatch, fake_class) -> None:
    """Prevent capture tests from selecting a real pyrtlsdr implementation."""
    monkeypatch.setitem(sys.modules, "rtlsdr", rtlsdr_module)
    monkeypatch.setattr(rtlsdr_module, "RtlSdr", fake_class, raising=False)
    monkeypatch.setattr(rtlsdr_module, "RtlSdrAio", fake_class, raising=False)


def test_capture_loop_tunes_reads_and_decodes_one_band(monkeypatch, tmp_path: Path):
    """Exercise the real tune -> read_samples -> decode sequence in _capture_loop.

    This is the code that actually talks to pyrtlsdr (set_center_freq,
    set_sample_rate, set_gain, read_samples, close) and previously had no
    coverage at all -- run_capture_cycle() (tested above) bypasses it
    entirely via an injected capture_fn. Mocks the rtlsdr binding and the
    wsprd decoder so the test is deterministic and needs no hardware.
    """
    _SyncFakeRtlSdr.created.clear()
    _patch_rtlsdr_classes(monkeypatch, _SyncFakeRtlSdr)

    # Schedule-sync uses time.time() to align to the next even WSPR minute;
    # feed a sequence that skips the (real-time) wait and then deterministically
    # ends the synchronous read loop after exactly one read_samples() call.
    fake_times = iter([60.0, 1000.0, 1000.0, 1000.0, 1010.0])
    monkeypatch.setattr(time, "time", lambda: next(fake_times, 1010.0))

    cfg = _station_cfg()
    cap = WsprCapture(
        bands_hz=[14080000],
        capture_duration_s=5,
        data_dir=tmp_path / "data",
        station_config=cfg,
    )

    def _fake_run_wsprd_subprocess(self, iq_data, band_hz, keep_temp=False):
        assert iq_data  # captured IQ bytes were actually handed to the decoder
        cap._stop_event.set()  # end the outer band-cycling loop after this spot
        yield {
            "timestamp": "2025-11-08 12:34:00",
            "call": "K1ABC",
            "grid": "FN42",
            "snr_db": -12,
        }

    monkeypatch.setattr(
        decoder_module.WsprDecoder, "run_wsprd_subprocess", _fake_run_wsprd_subprocess
    )

    cap._capture_loop()

    assert len(_SyncFakeRtlSdr.created) == 1
    sdr = _SyncFakeRtlSdr.created[0]
    assert sdr.center_freq == 14080000
    assert sdr.sample_rate == 1_200_000
    assert sdr.gain == 35
    assert sdr.read_calls >= 1
    assert sdr.closed is True
    assert cap.is_running() is False

    spots_file = tmp_path / "data" / "wspr_spots.jsonl"
    persisted = json.loads(spots_file.read_text(encoding="utf-8").strip())
    assert persisted["call"] == "K1ABC"
    assert persisted["dial_freq_hz"] == 14080000
    assert persisted["reporter_callsign"] == cfg.callsign


def test_capture_loop_no_devices_found(monkeypatch, tmp_path: Path):
    class _NoDeviceRtlSdr:
        @staticmethod
        def get_device_count() -> int:
            return 0

    _patch_rtlsdr_classes(monkeypatch, _NoDeviceRtlSdr)

    cap = WsprCapture(bands_hz=[14080000], data_dir=tmp_path / "data")
    cap._running = True

    cap._capture_loop()

    assert cap.is_running() is False


def test_start_is_idempotent_and_stop_without_start_is_safe(tmp_path: Path):
    cap = WsprCapture(bands_hz=[14080000], data_dir=tmp_path / "data")

    # stop() before start() should be a safe no-op, not raise.
    cap.stop()
    assert cap.is_running() is False

    cap.start()
    assert cap.is_running() is True
    # A second start() while already running should warn and return, not
    # spawn a second background thread.
    first_thread = cap._thread
    cap.start()
    assert cap._thread is first_thread

    cap.stop()
    assert cap.is_running() is False


def test_spots_log_retention_configurable_via_env_var(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(SPOTS_LOG_RETENTION_ENV_VAR, "5")
    cap = WsprCapture(bands_hz=[14080000], data_dir=tmp_path / "data")
    assert cap._spots_writer.retention_weeks == 5


def test_spots_log_retention_defaults_to_twelve_weeks(monkeypatch, tmp_path: Path):
    monkeypatch.delenv(SPOTS_LOG_RETENTION_ENV_VAR, raising=False)
    cap = WsprCapture(bands_hz=[14080000], data_dir=tmp_path / "data")
    assert cap._spots_writer.retention_weeks == 12
