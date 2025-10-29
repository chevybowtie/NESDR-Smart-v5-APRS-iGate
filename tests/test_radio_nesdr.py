"""Unit tests for the NESDR radio backend."""

from __future__ import annotations

import types
from typing import Any

import pytest

from neo_igate.radio.base import RadioError, RadioSettings
from neo_igate.radio import nesdr


class _DummySdr:
    def __init__(self) -> None:
        self.sample_rate = None
        self.center_freq = None
        self.freq_correction = None
        self.gain = None
        self.buffer_length = None
        self.read_buffer_size = None
        self.serial_number = "ABC123"
        self.closed = False
        self.read_calls: list[int] = []

    def read_samples(self, num_samples: int) -> list[complex]:
        self.read_calls.append(num_samples)
        return [0j] * num_samples

    def close(self) -> None:
        self.closed = True

    def set_manual_gain_enabled(self, enabled: bool) -> None:
        self.gain = "auto" if not enabled else self.gain


@pytest.fixture
def dummy_sdr(monkeypatch: pytest.MonkeyPatch) -> _DummySdr:
    dummy = _DummySdr()

    class DummyRtl:
        def __init__(self, device_index: int = 0) -> None:
            self.device_index = device_index
            self._inner = dummy

        def __getattr__(self, item: str) -> Any:
            return getattr(self._inner, item)

        def __setattr__(self, key: str, value: Any) -> None:
            if key in {"device_index", "_inner"}:
                super().__setattr__(key, value)
            else:
                setattr(self._inner, key, value)

    monkeypatch.setattr(nesdr, "RtlSdr", DummyRtl)
    monkeypatch.setattr(nesdr, "_RTLSDR_IMPORT_ERROR", None)
    return dummy


def test_open_initialises_device(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend(device_index=1)
    backend.open()
    assert backend._sdr is not None  # type: ignore[attr-defined]
    assert backend._sdr.device_index == 1  # type: ignore[attr-defined]


def test_open_skips_if_already_open(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    backend.open()
    existing = backend._sdr
    backend.open()
    assert backend._sdr is existing


def test_open_raises_when_module_missing(dummy_sdr, monkeypatch) -> None:
    monkeypatch.setattr(nesdr, "RtlSdr", None)
    monkeypatch.setattr(nesdr, "_RTLSDR_IMPORT_ERROR", ImportError("missing"))
    backend = nesdr.NESDRBackend()
    with pytest.raises(RadioError):
        backend.open()


def test_configure_applies_settings(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    settings = RadioSettings(
        center_frequency=144_390_000.0,
        sample_rate=1_024_000.0,
        gain=35.5,
        ppm=2,
        buffer_length=4096,
    )
    backend.configure(settings)
    assert dummy_sdr.sample_rate == settings.sample_rate
    assert dummy_sdr.center_freq == settings.center_frequency
    assert dummy_sdr.freq_correction == settings.ppm
    assert dummy_sdr.gain == settings.gain
    assert dummy_sdr.read_buffer_size == settings.buffer_length
    assert backend._settings == settings  # type: ignore[attr-defined]


def test_configure_auto_gain(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    settings = RadioSettings(
        center_frequency=144_390_000.0,
        sample_rate=1_024_000.0,
        gain=None,
    )
    backend.configure(settings)
    assert dummy_sdr.gain == "auto"


def test_read_samples_requires_open(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    with pytest.raises(RadioError):
        backend.read_samples(1024)


def test_read_samples_returns_data(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    backend.open()
    samples = list(backend.read_samples(256))
    assert len(samples) == 256
    assert dummy_sdr.read_calls == [256]


def test_get_status_without_open(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    status = backend.get_status()
    assert status.serial is None
    assert status.device == "NESDR Smart v5"


def test_get_status_with_device(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    backend.open()
    status = backend.get_status()
    assert status.serial == "ABC123"
    assert status.center_frequency is None  # untouched until configure


def test_close_releases_device(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    backend.open()
    backend.close()
    assert backend._sdr is None
    assert dummy_sdr.closed is True


def test_context_manager_opens_and_closes(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    with backend as handle:
        assert handle._sdr is not None  # type: ignore[attr-defined]
    assert backend._sdr is None
    assert dummy_sdr.closed is True


def test_read_samples_error_wrapped(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    backend.open()

    def fail(self, _num: int) -> list[complex]:  # type: ignore[override]
        raise RuntimeError("boom")

    backend._sdr.read_samples = types.MethodType(fail, backend._sdr)  # type: ignore[attr-defined]
    with pytest.raises(RadioError):
        backend.read_samples(10)


def test_configure_handles_exceptions(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    backend.open()

    class FailingSdr:
        def __init__(self) -> None:
            self.center_freq = None
            self.freq_correction = None
            self.gain = None
            self.read_buffer_size = None
            self.serial_number = "FAIL"
            self.closed = False

        @property
        def sample_rate(self) -> float | None:
            return None

        @sample_rate.setter
        def sample_rate(self, value: float) -> None:
            raise RuntimeError("boom")

        def set_manual_gain_enabled(self, _enabled: bool) -> None:
            pass

        def read_samples(self, num_samples: int) -> list[complex]:
            return [0j] * num_samples

        def close(self) -> None:
            self.closed = True

    backend._sdr = FailingSdr()  # type: ignore[assignment]
    with pytest.raises(RadioError):
        backend.configure(RadioSettings(center_frequency=1.0, sample_rate=1.0))


def test_close_wraps_errors(dummy_sdr) -> None:
    backend = nesdr.NESDRBackend()
    backend.open()

    def fail(self) -> None:
        raise RuntimeError("boom")

    backend._sdr.close = types.MethodType(fail, backend._sdr)  # type: ignore[attr-defined]
    with pytest.raises(RadioError):
        backend.close()
