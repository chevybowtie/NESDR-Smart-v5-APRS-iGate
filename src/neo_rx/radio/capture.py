"""Utility helpers for producing audio via rtl_fm."""

from __future__ import annotations

from collections import deque
import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import Deque, IO, Sequence


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
        self._stderr_thread: threading.Thread | None = None
        self._stderr_buffer: Deque[str] = deque(maxlen=8)

    @property
    def command(self) -> list[str] | None:
        """Return a copy of the last command issued to rtl_fm, if any."""
        return list(self._command) if self._command is not None else None

    def start(self) -> None:
        """Launch rtl_fm with the configured parameters."""

        if self._process is not None:
            raise AudioCaptureError("rtl_fm capture already started")
        if shutil.which("rtl_fm") is None:
            raise AudioCaptureError(
                "rtl_fm command not found in PATH; install rtl-sdr package"
            )

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

        self._stderr_buffer.clear()

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

        self._start_stderr_drain()

    def read(self, num_bytes: int) -> bytes:
        """Read a chunk of demodulated audio from rtl_fm."""

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
        self._join_stderr_thread(clear_buffer=False)
        stderr_tail = self._collect_stderr_tail()
        detail = _format_exit_detail(return_code, stderr_tail)
        self._stderr_buffer.clear()
        raise AudioCaptureError(detail)

    def stop(self) -> None:
        """Terminate the rtl_fm subprocess if it is running."""

        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
        finally:
            self._process = None
            self._join_stderr_thread()

    def __enter__(self) -> "RtlFmAudioCapture":
        """Start capture when entering a context manager block."""
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Ensure rtl_fm terminates on context manager exit."""
        self.stop()

    def _start_stderr_drain(self) -> None:
        if self._process is None or self._process.stderr is None:
            return

        def _worker(stream: IO[bytes]) -> None:
            try:
                while True:
                    chunk = stream.readline()
                    if not chunk:
                        break
                    text = chunk.decode("utf-8", errors="replace").strip()
                    if text:
                        self._stderr_buffer.append(text)
            finally:
                try:
                    stream.close()
                except OSError:
                    pass

        self._stderr_thread = threading.Thread(
            target=_worker,
            args=(self._process.stderr,),
            name="rtl_fm-stderr",
            daemon=True,
        )
        self._stderr_thread.start()

    def _collect_stderr_tail(self) -> str:
        if not self._stderr_buffer:
            return ""
        return " | ".join(self._stderr_buffer)

    def _join_stderr_thread(self, *, clear_buffer: bool = True) -> None:
        thread = self._stderr_thread
        self._stderr_thread = None
        if thread is None:
            return
        thread.join(timeout=0.5)
        if clear_buffer:
            self._stderr_buffer.clear()


_STDERR_HINTS: tuple[tuple[str, str], ...] = (
    (
        "usb_claim_interface",
        "rtl_fm could not claim the SDR. Stop other applications (neo-rx, rtl_tcp, etc.) that might be using the dongle, or unplug/replug it.",
    ),
    (
        "usb_open error",
        "rtl_fm could not open the SDR. Ensure no other software is using the device and that udev permissions are configured.",
    ),
    (
        "failed to open rtlsdr device",
        "The RTL-SDR refused to open. Check USB permissions and ensure DVB drivers like dvb_usb_rtl28xxu are detached.",
    ),
)


def _format_exit_detail(return_code: int, stderr_tail: str) -> str:
    detail = f"rtl_fm exited unexpectedly with code {return_code}"
    if not stderr_tail:
        return detail

    detail = f"{detail} — stderr tail: {stderr_tail}"
    lower_tail = stderr_tail.lower()
    hints = [hint for needle, hint in _STDERR_HINTS if needle in lower_tail]
    if hints:
        detail = f"{detail}\nHint: {' '.join(hints)}"
    return detail
