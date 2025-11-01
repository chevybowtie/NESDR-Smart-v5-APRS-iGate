"""Shared interface for SDR backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable


class RadioError(RuntimeError):
    """Raised when the radio backend encounters a recoverable error."""


@dataclass(slots=True)
class RadioSettings:
    """Parameters used to configure an SDR front-end."""

    center_frequency: float
    sample_rate: float
    gain: float | str | None = None
    ppm: int | None = None
    buffer_length: int | None = None


@dataclass(slots=True)
class RadioStatus:
    """Snapshot of SDR state for diagnostics."""

    device: str | None
    serial: str | None
    center_frequency: float | None
    sample_rate: float | None
    gain: float | str | None
    ppm: int | None


class RadioBackend(ABC):
    """Common API for interacting with SDR hardware."""

    @abstractmethod
    def open(self) -> None:
        """Initialise communication with the SDR hardware."""

    @abstractmethod
    def configure(self, settings: RadioSettings) -> None:
        """Apply tuning parameters to the hardware."""

    @abstractmethod
    def read_samples(self, num_samples: int) -> Iterable[complex]:
        """Return a batch of complex IQ samples."""

    @abstractmethod
    def get_status(self) -> RadioStatus:
        """Return diagnostic information about the SDR backend."""

    @abstractmethod
    def close(self) -> None:
        """Release hardware resources."""
