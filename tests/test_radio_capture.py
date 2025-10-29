"""Tests for rtl_fm audio capture helper."""

from __future__ import annotations

import io
from typing import Any

import pytest

from neo_igate.radio.capture import (  # type: ignore[import]
    AudioCaptureError,
    RtlFmAudioCapture,
    RtlFmConfig,
)


class _FakeProcess:
    def __init__(
        self,
        args: list[str],
        *,
        data: bytes = b"\x00" * 8,
        return_code: int | None = None,
    ) -> None:
        self.args = args
        self.stdout = io.BytesIO(data)
        self.stderr = io.BytesIO()
        self._return_code = return_code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self._return_code

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int | None:
        return self._return_code

    def kill(self) -> None:
        self.killed = True


def test_rtl_fm_capture_builds_command(monkeypatch) -> None:
    launch_args: list[list[str]] = []

    def fake_which(cmd: str) -> str | None:  # pragma: no cover - trivial
        return "/usr/bin/rtl_fm" if cmd == "rtl_fm" else None

    def fake_popen(args: list[str], **_: Any) -> _FakeProcess:
        launch_args.append(args)
        return _FakeProcess(args, data=b"abcdEFGH")

    monkeypatch.setattr("neo_igate.radio.capture.shutil.which", fake_which)
    monkeypatch.setattr("neo_igate.radio.capture.subprocess.Popen", fake_popen)

    config = RtlFmConfig(
        frequency_hz=144_390_000,
        gain=35,
        ppm=1,
        squelch_db=-30,
        additional_args=("-n", "16384"),
    )
    capture = RtlFmAudioCapture(config)

    capture.start()
    assert launch_args
    expected = [
        "rtl_fm",
        "-d",
        "0",
        "-f",
        "144390000",
        "-M",
        "fm",
        "-s",
        "22050",
        "-E",
        "deemp",
        "-A",
        "fast",
        "-F",
        "9",
        "-g",
        "35",
        "-p",
        "1",
        "-l",
        "-30",
        "-n",
        "16384",
    ]
    assert capture.command == expected
    chunk = capture.read(4)
    assert chunk == b"abcd"
    capture.stop()


def test_rtl_fm_missing_command(monkeypatch) -> None:
    monkeypatch.setattr("neo_igate.radio.capture.shutil.which", lambda _: None)
    capture = RtlFmAudioCapture(RtlFmConfig(frequency_hz=144_390_000))

    with pytest.raises(AudioCaptureError):
        capture.start()


def test_rtl_fm_unexpected_exit(monkeypatch) -> None:
    def fake_which(cmd: str) -> str | None:
        return "/usr/bin/rtl_fm" if cmd == "rtl_fm" else None

    class _EmptyProcess(_FakeProcess):
        def __init__(self, args: list[str]) -> None:
            super().__init__(args, data=b"", return_code=1)

        def poll(self) -> int | None:
            return 1

    def fake_popen(args: list[str], **_: Any) -> _FakeProcess:
        return _EmptyProcess(args)

    monkeypatch.setattr("neo_igate.radio.capture.shutil.which", fake_which)
    monkeypatch.setattr("neo_igate.radio.capture.subprocess.Popen", fake_popen)

    capture = RtlFmAudioCapture(RtlFmConfig(frequency_hz=144_390_000))
    capture.start()

    with pytest.raises(AudioCaptureError) as exc:
        capture.read(8)
    assert "exited unexpectedly" in str(exc.value)
    capture.stop()
