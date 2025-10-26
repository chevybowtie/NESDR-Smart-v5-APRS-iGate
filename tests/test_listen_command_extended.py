"""Additional tests for the listen command error handling and helpers."""

from __future__ import annotations

import io
from argparse import Namespace
from queue import Queue
from types import SimpleNamespace
from typing import Any, cast

import pytest

from nesdr_igate.commands import listen
from nesdr_igate.config import StationConfig
from nesdr_igate.radio.capture import AudioCaptureError
from nesdr_igate.aprs.kiss_client import KISSClientError


def _patch_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    class _SignalState:
        handler: Any = object()

    def fake_getsignal(sig: int):  # type: ignore[no-untyped-def]
        return _SignalState.handler

    def fake_signal(sig: int, handler: Any):  # type: ignore[no-untyped-def]
        _SignalState.handler = handler
        return handler

    monkeypatch.setattr(listen.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(listen.signal, "signal", fake_signal)


def test_resolve_direwolf_config_prefers_local(tmp_path) -> None:
    local = tmp_path / "direwolf.conf"
    local.write_text("local", encoding="utf-8")
    assert listen._resolve_direwolf_config(tmp_path) == local


def test_resolve_direwolf_config_fallback(tmp_path, monkeypatch) -> None:
    fallback_dir = tmp_path / "fallback"
    fallback_dir.mkdir()
    fallback = fallback_dir / "direwolf.conf"
    fallback.write_text("fallback", encoding="utf-8")
    monkeypatch.setattr(listen.config_module, "get_config_dir", lambda: fallback_dir)
    assert listen._resolve_direwolf_config(tmp_path) == fallback


def test_wait_for_kiss_success_after_retry(monkeypatch) -> None:
    attempts: list[int] = []

    class DummyClient:
        def __init__(self) -> None:
            self.calls = 0

        def connect(self) -> None:
            attempts.append(self.calls)
            if self.calls < 2:
                self.calls += 1
                raise KISSClientError("fail")
            self.calls += 1

    dummy = DummyClient()
    result = listen._wait_for_kiss(cast(listen.KISSClient, dummy), attempts=3, delay=0.0)
    assert result is True
    assert dummy.calls == 3


def test_wait_for_kiss_exhausts_attempts() -> None:
    class DummyClient:
        def connect(self) -> None:
            raise KISSClientError("still failing")

    dummy = DummyClient()
    result = listen._wait_for_kiss(cast(listen.KISSClient, dummy), attempts=2, delay=0.0)
    assert result is False


def test_display_frame_truncates_output(capsys) -> None:
    payload = "A" * 200
    listen._display_frame(5, 1, payload)
    captured = capsys.readouterr()
    assert "[000005]" in captured.out
    assert payload[:117] in captured.out
    assert payload not in captured.out


def test_report_audio_error_prints_message(capsys) -> None:
    queue: Queue[Exception] = Queue()
    queue.put(RuntimeError("oops"))
    listen._report_audio_error(queue)
    captured = capsys.readouterr()
    assert "Audio pipeline error" in captured.out


def test_run_listen_config_missing(monkeypatch, tmp_path, capsys) -> None:
    _patch_signal(monkeypatch)
    config_path = tmp_path / "config.toml"

    monkeypatch.setattr(listen.config_module, "resolve_config_path", lambda *_: config_path)

    def fake_load(_path):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("missing")

    monkeypatch.setattr(listen.config_module, "load_config", fake_load)

    exit_code = listen.run_listen(Namespace(config=None))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Config not found" in captured.out


def test_run_listen_config_invalid(monkeypatch, tmp_path, capsys) -> None:
    _patch_signal(monkeypatch)
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(listen.config_module, "resolve_config_path", lambda *_: config_path)

    def fake_load(_path):  # type: ignore[no-untyped-def]
        raise ValueError("bad")

    monkeypatch.setattr(listen.config_module, "load_config", fake_load)

    exit_code = listen.run_listen(Namespace(config=None))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Config invalid" in captured.out


def test_run_listen_missing_direwolf_config(monkeypatch, tmp_path, capsys) -> None:
    _patch_signal(monkeypatch)
    config_path = tmp_path / "config.toml"
    config_dir = config_path.parent
    monkeypatch.setattr(listen.config_module, "resolve_config_path", lambda *_: config_path)
    monkeypatch.setattr(listen.config_module, "load_config", lambda *_: StationConfig(callsign="N0CALL-10", passcode="12345"))
    monkeypatch.setattr(listen.config_module, "get_config_dir", lambda: tmp_path / "global")

    exit_code = listen.run_listen(Namespace(config=None))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Direwolf configuration missing" in captured.out
    assert config_dir == config_path.parent


def test_run_listen_audio_capture_failure(monkeypatch, tmp_path, capsys) -> None:
    _patch_signal(monkeypatch)
    config_path = tmp_path / "config.toml"
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "direwolf.conf").write_text("test", encoding="utf-8")

    cfg = StationConfig(callsign="N0CALL-10", passcode="12345")

    monkeypatch.setattr(listen.config_module, "resolve_config_path", lambda *_: config_path)
    monkeypatch.setattr(listen.config_module, "load_config", lambda *_: cfg)

    class FailingCapture:
        def __init__(self, _cfg):
            self.stopped = False

        def start(self) -> None:
            raise AudioCaptureError("device not found")

        def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr(listen, "RtlFmAudioCapture", FailingCapture)

    exit_code = listen.run_listen(Namespace(config=None))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Audio capture failed" in captured.out


def test_run_listen_direwolf_launch_failure(monkeypatch, tmp_path, capsys) -> None:
    _patch_signal(monkeypatch)
    config_path = tmp_path / "config.toml"
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "direwolf.conf").write_text("test", encoding="utf-8")

    cfg = StationConfig(callsign="N0CALL-10", passcode="12345")

    class DummyCapture:
        def __init__(self, _cfg):
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr(listen, "RtlFmAudioCapture", DummyCapture)
    monkeypatch.setattr(listen.config_module, "resolve_config_path", lambda *_: config_path)
    monkeypatch.setattr(listen.config_module, "load_config", lambda *_: cfg)

    def fake_popen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("boom")

    monkeypatch.setattr(listen.subprocess, "Popen", fake_popen)

    exit_code = listen.run_listen(Namespace(config=None))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Failed to start Direwolf" in captured.out


def test_run_listen_kiss_unreachable(monkeypatch, tmp_path, capsys) -> None:
    _patch_signal(monkeypatch)
    config_path = tmp_path / "config.toml"
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "direwolf.conf").write_text("test", encoding="utf-8")

    cfg = StationConfig(callsign="N0CALL-10", passcode="12345", kiss_host="127.0.0.1", kiss_port=9001)

    monkeypatch.setattr(listen.config_module, "resolve_config_path", lambda *_: config_path)
    monkeypatch.setattr(listen.config_module, "load_config", lambda *_: cfg)

    capture_instances: list[Any] = []

    class DummyCapture:
        def __init__(self, _cfg):
            self.started = False
            self.stopped = False
            capture_instances.append(self)

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

        def read(self, _size: int) -> bytes:
            return b""

    class FakeThread:
        def __init__(self, *_args, **_kwargs):
            self.started = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return False

        def join(self, *_args, **_kwargs) -> None:
            return None

    class DummyProc:
        def __init__(self, *_args, **_kwargs):
            self.pid = 1234
            self.stdin = io.BytesIO()
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, *_args, **_kwargs) -> int:
            return 0

    class DummyKISSClient:
        def __init__(self, *_args, **_kwargs):
            self.closed = False

        def connect(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(listen, "RtlFmAudioCapture", DummyCapture)
    monkeypatch.setattr(listen.threading, "Thread", FakeThread)
    monkeypatch.setattr(listen.subprocess, "Popen", lambda *_a, **_k: DummyProc())
    monkeypatch.setattr(listen, "KISSClient", DummyKISSClient)
    monkeypatch.setattr(listen, "_wait_for_kiss", lambda *_args, **_kwargs: False)

    exit_code = listen.run_listen(Namespace(config=None, no_aprsis=True))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Unable to connect to Direwolf KISS" in captured.out
    assert capture_instances and capture_instances[0].stopped is True