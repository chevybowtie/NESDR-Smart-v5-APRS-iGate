"""Utility helpers for producing audio via rtl_fm."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Sequence


class AudioCaptureError(RuntimeError):
    """Raised when rtl_fm based capture fails."""


@dataclass(slots=True)
class RtlFmConfig:
    """Parameters for launching rtl_fm as an audio source."""

    frequency_hz: float
    sample_rate: int = 22_050
    gain: float | str | None = None
    ppm: int = 0
    device_index: int = 0
    squelch_db: int | None = None
    additional_args: Sequence[str] | None = None


class RtlFmAudioCapture:
    """Manage an rtl_fm subprocess and expose its audio stream."""

    def __init__(self, config: RtlFmConfig) -> None:
        self._config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._command: list[str] | None = None

    @property
    def command(self) -> list[str] | None:
        """Return the most recent command used to launch rtl_fm."""
        return list(self._command) if self._command is not None else None

    def start(self) -> None:
        if self._process is not None:
            raise AudioCaptureError("rtl_fm capture already started")
        if shutil.which("rtl_fm") is None:
            raise AudioCaptureError("rtl_fm command not found in PATH; install rtl-sdr package")

        cmd: list[str] = [
            "rtl_fm",
            "-d",
            str(self._config.device_index),
            "-f",
            str(int(self._config.frequency_hz)),
            "-M",
            "fm",
            "-s",
            str(int(self._config.sample_rate)),
            "-E",
            "deemp",
            "-A",
            "fast",
            "-F",
            "9",
        ]

        if self._config.gain is not None:
            cmd.extend(["-g", str(self._config.gain)])
        if self._config.ppm:
            cmd.extend(["-p", str(self._config.ppm)])
        if self._config.squelch_db is not None:
            cmd.extend(["-l", str(self._config.squelch_db)])
        if self._config.additional_args:
            cmd.extend(self._config.additional_args)

        self._command = cmd

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except OSError as exc:
            raise AudioCaptureError(f"Failed to launch rtl_fm: {exc}") from exc

        if self._process.stdout is None:
            self.stop()
            raise AudioCaptureError("Failed to open rtl_fm stdout pipe")

    def read(self, num_bytes: int) -> bytes:
        if self._process is None or self._process.stdout is None:
            raise AudioCaptureError("rtl_fm capture not started")
        try:
            chunk = self._process.stdout.read(num_bytes)
        except OSError as exc:
            raise AudioCaptureError(f"Failed to read from rtl_fm: {exc}") from exc

        if chunk:
            return chunk

        return_code = self._process.poll()
        if return_code is None:
            return chunk
        raise AudioCaptureError(f"rtl_fm exited unexpectedly with code {return_code}")

    def stop(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
        finally:
            self._process = None

    def __enter__(self) -> "RtlFmAudioCapture":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()