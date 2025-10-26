"""Tests for setup hardware validation helpers."""

from __future__ import annotations

import io
import logging
import subprocess
from pathlib import Path

from nesdr_igate.commands import setup
from nesdr_igate.config import StationConfig


def test_extract_ppm_from_output_detects_value() -> None:
    sample = """
    Info: some status line
    Average offset -0.95 ppm after 10 seconds
    Done.
    """
    assert setup._extract_ppm_from_output(sample) == "Average offset -0.95 ppm after 10 seconds"


def test_extract_ppm_from_output_none() -> None:
    assert setup._extract_ppm_from_output("No relevant measurements") is None


def test_tail_file_returns_last_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "sample.log"
    log_file.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    assert setup._tail_file(log_file, lines=2) == ["three", "four"]


def _configure_caplog(caplog, level=logging.INFO) -> None:
    caplog.set_level(level, logger="nesdr_igate.commands.setup")
    caplog.clear()


def test_report_direwolf_log_summary_missing(tmp_path: Path, monkeypatch, caplog) -> None:
    _configure_caplog(caplog, level=logging.WARNING)
    monkeypatch.setattr("nesdr_igate.commands.setup.config_module.get_data_dir", lambda: tmp_path)

    setup._report_direwolf_log_summary()
    assert "Direwolf log not found" in caplog.text


def test_report_direwolf_log_summary_includes_recent_lines(tmp_path: Path, monkeypatch, caplog) -> None:
    _configure_caplog(caplog)
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "direwolf.log"
    log_file.write_text("\n".join(f"line {i}" for i in range(8)), encoding="utf-8")

    monkeypatch.setattr("nesdr_igate.commands.setup.config_module.get_data_dir", lambda: tmp_path)

    setup._report_direwolf_log_summary()
    assert "[OK     ] Direwolf log found" in caplog.text
    # Only the last six lines should be printed
    for index in range(2, 8):
        assert f"line {index}" in caplog.text


def test_can_launch_direwolf_true(monkeypatch) -> None:
    monkeypatch.setattr("nesdr_igate.commands.setup.shutil.which", lambda cmd: f"/usr/bin/{cmd}")

    assert setup._can_launch_direwolf() is True


def test_can_launch_direwolf_false(monkeypatch) -> None:
    monkeypatch.setattr("nesdr_igate.commands.setup.shutil.which", lambda cmd: None if cmd == "direwolf" else f"/usr/bin/{cmd}")

    assert setup._can_launch_direwolf() is False


def test_launch_direwolf_probe_missing_config(tmp_path: Path, monkeypatch, caplog) -> None:
    _configure_caplog(caplog, level=logging.WARNING)
    monkeypatch.setattr("nesdr_igate.commands.setup.config_module.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nesdr_igate.commands.setup.config_module.get_config_dir", lambda: tmp_path)

    config = StationConfig(callsign="N0CALL-10", passcode="12345")

    setup._launch_direwolf_probe(config)
    assert "direwolf.conf not found" in caplog.text


class _FakeRtlProcess:
    def __init__(self) -> None:
        self.stdout = io.BytesIO(b"synthetic audio")
        self.terminated = False
        self.killed = False
        self.wait_timeouts: list[float | None] = []

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        return 0

    def kill(self) -> None:
        self.killed = True


class _FakeDirewolfProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.wait_timeouts: list[float | None] = []

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        return 0

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def test_launch_direwolf_probe_success(tmp_path: Path, monkeypatch, caplog) -> None:
    _configure_caplog(caplog)
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    (config_dir / "direwolf.conf").write_text("test", encoding="utf-8")

    monkeypatch.setattr("nesdr_igate.commands.setup.config_module.get_data_dir", lambda: data_dir)
    monkeypatch.setattr("nesdr_igate.commands.setup.config_module.get_config_dir", lambda: config_dir)

    rtl_process = _FakeRtlProcess()
    direwolf_process = _FakeDirewolfProcess()

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if cmd[0] == "rtl_fm":
            return rtl_process
        if cmd[0] == "direwolf":
            log_handle = kwargs.get("stdout")
            assert log_handle is not None
            log_handle.write("Direwolf started\n")
            log_handle.write("Frame decoded\n")
            log_handle.flush()
            return direwolf_process
        raise AssertionError(f"Unexpected command {cmd}")

    monkeypatch.setattr("nesdr_igate.commands.setup.subprocess.Popen", fake_popen)

    config = StationConfig(
        callsign="N0CALL-10",
        passcode="12345",
        center_frequency_hz=144_390_000.0,
        gain=35,
        ppm_correction=1,
    )

    setup._launch_direwolf_probe(config)

    assert "[OK     ] Direwolf probe log" in caplog.text
    assert "Frame decoded" in caplog.text
    assert rtl_process.terminated is True
    assert rtl_process.wait_timeouts == [5]
    assert direwolf_process.wait_timeouts == [15]


def test_launch_direwolf_probe_direwolf_timeout(tmp_path: Path, monkeypatch, caplog) -> None:
    _configure_caplog(caplog)
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    (config_dir / "direwolf.conf").write_text("test", encoding="utf-8")

    monkeypatch.setattr("nesdr_igate.commands.setup.config_module.get_data_dir", lambda: data_dir)
    monkeypatch.setattr("nesdr_igate.commands.setup.config_module.get_config_dir", lambda: config_dir)

    rtl_process = _FakeRtlProcess()

    class TimeoutDirewolfProcess(_FakeDirewolfProcess):
        def wait(self, timeout: float | None = None) -> int:  # type: ignore[override]
            if timeout == 15:
                raise subprocess.TimeoutExpired(cmd="direwolf", timeout=timeout)
            return super().wait(timeout)

    direwolf_process = TimeoutDirewolfProcess()

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if cmd[0] == "rtl_fm":
            return rtl_process
        if cmd[0] == "direwolf":
            log_handle = kwargs.get("stdout")
            assert log_handle is not None
            log_handle.write("timeout test\n")
            log_handle.flush()
            return direwolf_process
        raise AssertionError(f"Unexpected command {cmd}")

    monkeypatch.setattr("nesdr_igate.commands.setup.subprocess.Popen", fake_popen)

    config = StationConfig(callsign="N0CALL-10", passcode="12345")

    setup._launch_direwolf_probe(config)

    assert "timeout test" in caplog.text
    # Ensure cleanup still waited on the RTL process even after timeout
    assert rtl_process.terminated is True
    assert rtl_process.wait_timeouts == [5]
    assert direwolf_process.terminated is True
    assert 5 in direwolf_process.wait_timeouts