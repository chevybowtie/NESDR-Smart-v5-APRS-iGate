"""NESDR Smart v5 backend implementation."""

from __future__ import annotations

from typing import Iterable

try:
    from rtlsdr import RtlSdr  # type: ignore[import]
except ImportError as import_error:  # pragma: no cover - handled via runtime error
    RtlSdr = None  # type: ignore[assignment]
    _RTLSDR_IMPORT_ERROR = import_error
else:
    _RTLSDR_IMPORT_ERROR = None

from .base import RadioBackend, RadioError, RadioSettings, RadioStatus


class NESDRBackend(RadioBackend):
    """Concrete backend for the NESDR Smart v5 dongle."""

    def __init__(self, device_index: int = 0) -> None:
        self._device_index = device_index
        self._sdr: RtlSdr | None = None  # type: ignore[name-defined]
        self._settings: RadioSettings | None = None

    def open(self) -> None:
        """Initialise the RTL-SDR handle."""
        if self._sdr is not None:
            return
        if (
            RtlSdr is None
        ):  # pragma: no cover - exercised in environments without pyrtlsdr
            raise RadioError(
                "pyrtlsdr (rtlsdr module) is not installed; please `pip install pyrtlsdr`."
            ) from _RTLSDR_IMPORT_ERROR
        try:
            self._sdr = RtlSdr(device_index=self._device_index)
        except Exception as exc:  # pragma: no cover - hardware-specific failures
            raise RadioError(
                f"Failed to open NESDR device index {self._device_index}: {exc}"
            ) from exc

    def configure(self, settings: RadioSettings) -> None:
        """Apply tuner settings using pyrtlsdr."""
        if self._sdr is None:
            self.open()
        assert self._sdr is not None  # for type checkers
        try:
            self._sdr.sample_rate = settings.sample_rate
            self._sdr.center_freq = settings.center_frequency
            if settings.ppm is not None:
                self._sdr.freq_correction = settings.ppm
            if settings.gain is not None:
                self._sdr.gain = settings.gain
            else:
                self._sdr.set_manual_gain_enabled(False)
            if settings.buffer_length is not None:
                self._sdr.read_buffer_size = settings.buffer_length
        except Exception as exc:  # pragma: no cover - hardware-specific failures
            raise RadioError(f"Failed to configure NESDR: {exc}") from exc
        self._settings = settings

    def read_samples(self, num_samples: int) -> Iterable[complex]:
        """Fetch IQ samples from the SDR."""
        if self._sdr is None:
            raise RadioError(
                "NESDR backend is not open; call open() before reading samples"
            )
        try:
            return self._sdr.read_samples(num_samples)
        except Exception as exc:  # pragma: no cover - hardware-specific failures
            raise RadioError(f"Failed to read samples: {exc}") from exc

    def get_status(self) -> RadioStatus:
        """Return device metadata useful for diagnostics."""
        if self._sdr is None:
            return RadioStatus(
                device="NESDR Smart v5",
                serial=None,
                center_frequency=self._settings.center_frequency
                if self._settings
                else None,
                sample_rate=self._settings.sample_rate if self._settings else None,
                gain=self._settings.gain if self._settings else None,
                ppm=self._settings.ppm if self._settings else None,
            )
        serial = getattr(self._sdr, "serial_number", None)
        return RadioStatus(
            device="NESDR Smart v5",
            serial=str(serial) if serial is not None else None,
            center_frequency=getattr(self._sdr, "center_freq", None),
            sample_rate=getattr(self._sdr, "sample_rate", None),
            gain=getattr(self._sdr, "gain", None),
            ppm=getattr(self._sdr, "freq_correction", None),
        )

    def close(self) -> None:
        """Release the RTL-SDR handle."""
        if self._sdr is None:
            return
        try:
            self._sdr.close()
        except Exception as exc:  # pragma: no cover - hardware-specific failures
            raise RadioError(f"Failed to close NESDR device: {exc}") from exc
        finally:
            self._sdr = None

    def __enter__(self) -> "NESDRBackend":  # pragma: no cover - trivial wrapper
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial wrapper
        self.close()
