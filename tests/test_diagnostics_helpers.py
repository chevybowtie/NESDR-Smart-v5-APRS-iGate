"""Tests for diagnostics helper utilities."""

from __future__ import annotations

import shutil
from pathlib import Path

from neo_core import diagnostics_helpers as helpers


def test_probe_tcp_endpoint_success(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class DummyConnection:
        def __enter__(self) -> "DummyConnection":
            calls["entered"] = True
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
            calls["exited"] = True
            return None

    times = iter([100.0, 100.123])

    def fake_perf_counter() -> float:
        return next(times)

    def fake_create_connection(address, timeout=None):  # type: ignore[no-untyped-def]
        calls["address"] = address
        calls["timeout"] = timeout
        return DummyConnection()

    monkeypatch.setattr(helpers.time, "perf_counter", fake_perf_counter)
    monkeypatch.setattr(helpers.socket, "create_connection", fake_create_connection)

    result = helpers.probe_tcp_endpoint("example.com", 14580, timeout=2.5)

    assert result.success is True
    assert result.error is None
    assert result.latency_ms == 123.0
    assert calls["address"] == ("example.com", 14580)
    assert calls["timeout"] == 2.5
    assert calls["entered"] and calls["exited"]


def test_probe_tcp_endpoint_failure(monkeypatch) -> None:
    def fake_create_connection(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("connection refused")

    monkeypatch.setattr(helpers.socket, "create_connection", fake_create_connection)

    result = helpers.probe_tcp_endpoint("bad.example", 9999, timeout=0.1)

    assert result.success is False
    assert result.latency_ms is None
    assert "connection refused" in (result.error or "")


def test_check_disk_space_ok(monkeypatch, tmp_path: Path) -> None:
    def fake_disk_usage(_path):
        return _DiskUsage(total=100_000, used=50_000, free=50_000)

    monkeypatch.setattr(helpers.shutil, "disk_usage", fake_disk_usage)

    result = helpers.check_disk_space(tmp_path)

    assert result.status == "ok"
    assert result.details["percent_free"] == 50.0
    assert str(tmp_path) in result.message


def test_check_disk_space_warning_below_threshold(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(helpers.DISK_WARN_PERCENT_ENV_VAR, raising=False)
    monkeypatch.delenv(helpers.DISK_ERROR_PERCENT_ENV_VAR, raising=False)

    def fake_disk_usage(_path):
        return _DiskUsage(total=100_000, used=92_000, free=8_000)

    monkeypatch.setattr(helpers.shutil, "disk_usage", fake_disk_usage)

    result = helpers.check_disk_space(tmp_path)

    assert result.status == "warning"
    assert result.details["percent_free"] == 8.0


def test_check_disk_space_error_below_threshold(monkeypatch, tmp_path: Path) -> None:
    def fake_disk_usage(_path):
        return _DiskUsage(total=100_000, used=98_000, free=2_000)

    monkeypatch.setattr(helpers.shutil, "disk_usage", fake_disk_usage)

    result = helpers.check_disk_space(tmp_path)

    assert result.status == "error"
    assert result.details["percent_free"] == 2.0


def test_check_disk_space_thresholds_configurable_via_env_var(
    monkeypatch, tmp_path: Path
) -> None:
    def fake_disk_usage(_path):
        return _DiskUsage(total=100_000, used=80_000, free=20_000)

    monkeypatch.setattr(helpers.shutil, "disk_usage", fake_disk_usage)
    monkeypatch.setenv(helpers.DISK_WARN_PERCENT_ENV_VAR, "50")

    result = helpers.check_disk_space(tmp_path)

    assert result.status == "warning"


def test_check_disk_space_handles_missing_path(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "does" / "not" / "exist"

    def fake_disk_usage(path):
        assert Path(path) == tmp_path
        return _DiskUsage(total=100_000, used=10_000, free=90_000)

    monkeypatch.setattr(helpers.shutil, "disk_usage", fake_disk_usage)

    result = helpers.check_disk_space(missing)

    assert result.status == "ok"


class _DiskUsage:
    def __init__(self, total: int, used: int, free: int) -> None:
        self.total = total
        self.used = used
        self.free = free
