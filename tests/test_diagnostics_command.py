"""Unit tests for diagnostics command helpers."""

from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path

from nesdr_igate.commands import diagnostics
from nesdr_igate.config import StationConfig, save_config


class _ProbeResult:
    def __init__(self, success: bool, *, latency_ms: float | None = None, error: str | None = None) -> None:
        self.success = success
        self.latency_ms = latency_ms
        self.error = error


def _fake_import_factory(original):
    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "rtlsdr":
            raise ImportError("mock missing module")
        return original(name, *args, **kwargs)

    return fake_import


def _fake_runtime_import_factory(original):
    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "rtlsdr":
            raise RuntimeError("mock runtime failure")
        return original(name, *args, **kwargs)

    return fake_import


def test_check_environment_reports_missing_packages(monkeypatch) -> None:
    monkeypatch.setattr(diagnostics.sys, "prefix", "/usr")
    monkeypatch.setattr(diagnostics.sys, "base_prefix", "/usr")

    def fake_version(package: str) -> str:
        if package == "pyrtlsdr":
            raise diagnostics.importlib_metadata.PackageNotFoundError
        return "1.0"

    monkeypatch.setattr(diagnostics.importlib_metadata, "version", fake_version)

    section = diagnostics._check_environment()

    assert section.status == "warning"
    assert "Missing packages" in section.message
    assert section.details["packages"]["pyrtlsdr"] is None


def test_check_environment_all_ok(monkeypatch) -> None:
    monkeypatch.setattr(diagnostics.sys, "prefix", "/env/venv")
    monkeypatch.setattr(diagnostics.sys, "base_prefix", "/usr")

    monkeypatch.setattr(diagnostics.importlib_metadata, "version", lambda _: "2.0")

    section = diagnostics._check_environment()

    assert section.status == "ok"
    assert "Required packages present" in section.message
    assert section.details["venv_active"] is True


def test_check_config_missing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    section, loaded = diagnostics._check_config(config_path)

    assert section.status == "warning"
    assert loaded is None
    assert "No config file" in section.message


def test_check_config_loads_successfully(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    cfg = StationConfig(callsign="N0CALL-10", passcode="12345")
    save_config(cfg, path=config_path)

    section, loaded = diagnostics._check_config(config_path)

    assert section.status == "ok"
    assert loaded is not None
    assert section.details["callsign"] == "N0CALL-10"


def test_check_config_load_failure(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("invalid", encoding="utf-8")

    def raise_error(path: Path) -> None:  # type: ignore[return-value]
        raise ValueError("boom")

    monkeypatch.setattr(diagnostics.config_module, "load_config", raise_error)

    section, loaded = diagnostics._check_config(config_path)

    assert section.status == "error"
    assert loaded is None
    assert "Failed to load configuration" in section.message


def test_check_sdr_import_error(monkeypatch) -> None:
    original_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", _fake_import_factory(original_import))

    section = diagnostics._check_sdr()

    assert section.status == "warning"
    assert "pyrtlsdr not installed" in section.message


def test_check_sdr_partial_install_runtime_error(monkeypatch) -> None:
    original_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", _fake_runtime_import_factory(original_import))

    section = diagnostics._check_sdr()

    assert section.status == "error"
    assert "failed to initialise" in section.message


def test_check_sdr_no_devices(monkeypatch) -> None:
    module = types.ModuleType("rtlsdr")

    class DummyRtl:
        @staticmethod
        def get_device_count() -> int:
            return 0

        @staticmethod
        def get_device_serial_addresses() -> list[bytes]:
            return [b"abc123"]

    setattr(module, "RtlSdr", DummyRtl)
    monkeypatch.setitem(sys.modules, "rtlsdr", module)

    section = diagnostics._check_sdr()

    assert section.status == "warning"
    assert section.details["device_count"] == 0


def test_check_sdr_with_devices(monkeypatch) -> None:
    module = types.ModuleType("rtlsdr")

    class DummyRtl:
        @staticmethod
        def get_device_count() -> int:
            return 2

        @staticmethod
        def get_device_serial_addresses() -> list[bytes]:
            return [b"serial1", b"serial2"]

    setattr(module, "RtlSdr", DummyRtl)
    monkeypatch.setitem(sys.modules, "rtlsdr", module)

    section = diagnostics._check_sdr()

    assert section.status == "ok"
    assert "2 RTL-SDR" in section.message
    assert section.details["serials"] == ["serial1", "serial2"]


def test_check_sdr_serial_probe_failure(monkeypatch) -> None:
    module = types.ModuleType("rtlsdr")

    class DummyRtl:
        @staticmethod
        def get_device_count() -> int:
            return 1

        @staticmethod
        def get_device_serial_addresses() -> list[str]:
            raise RuntimeError("no serials")

    setattr(module, "RtlSdr", DummyRtl)
    monkeypatch.setitem(sys.modules, "rtlsdr", module)

    section = diagnostics._check_sdr()

    assert section.status == "ok"
    assert section.details["device_count"] == 1
    assert "serials" not in section.details


def test_check_sdr_device_query_failure(monkeypatch) -> None:
    module = types.ModuleType("rtlsdr")

    class DummyRtl:
        @staticmethod
        def get_device_count() -> int:
            raise OSError("not ready")

    setattr(module, "RtlSdr", DummyRtl)
    monkeypatch.setitem(sys.modules, "rtlsdr", module)

    section = diagnostics._check_sdr()

    assert section.status == "error"
    assert "Failed to query" in section.message


def test_check_direwolf_success(monkeypatch) -> None:
    config = StationConfig(callsign="N0CALL-10", passcode="12345")

    monkeypatch.setattr(
        diagnostics,
        "probe_tcp_endpoint",
        lambda *_args, **_kwargs: _ProbeResult(True, latency_ms=12.3),
    )

    section = diagnostics._check_direwolf(config)

    assert section.status == "ok"
    assert section.details["latency_ms"] == 12.3


def test_check_direwolf_failure(monkeypatch) -> None:
    config = StationConfig(callsign="N0CALL-10", passcode="12345")

    monkeypatch.setattr(
        diagnostics,
        "probe_tcp_endpoint",
        lambda *_args, **_kwargs: _ProbeResult(False, error="timeout"),
    )

    section = diagnostics._check_direwolf(config)

    assert section.status == "warning"
    assert section.details["error"] == "timeout"


def test_check_direwolf_no_config() -> None:
    section = diagnostics._check_direwolf(None)

    assert section.status == "warning"
    assert "Configuration unavailable" in section.message


def test_check_aprs_is_success(monkeypatch) -> None:
    config = StationConfig(callsign="N0CALL-10", passcode="12345")

    monkeypatch.setattr(
        diagnostics,
        "probe_tcp_endpoint",
        lambda *_args, **_kwargs: _ProbeResult(True, latency_ms=45.6),
    )

    section = diagnostics._check_aprs_is(config)

    assert section.status == "ok"
    assert section.details["latency_ms"] == 45.6


def test_check_aprs_is_failure(monkeypatch) -> None:
    config = StationConfig(callsign="N0CALL-10", passcode="12345")

    monkeypatch.setattr(
        diagnostics,
        "probe_tcp_endpoint",
        lambda *_args, **_kwargs: _ProbeResult(False, error="reset"),
    )

    section = diagnostics._check_aprs_is(config)

    assert section.status == "warning"
    assert section.details["error"] == "reset"


def test_sections_to_mapping() -> None:
    section = diagnostics.Section("Sample", "ok", "message", {"a": 1})
    report = diagnostics._sections_to_mapping([section])

    assert report["sample"]["status"] == "ok"
    assert report["sample"]["details"] == {"a": 1}


def test_print_text_report_verbose(capsys) -> None:
    sections = [diagnostics.Section("Env", "ok", "ready", {"packages": {"numpy": "1.0"}})]

    diagnostics._print_text_report(sections, verbose=True)
    captured = capsys.readouterr()

    assert "[OK     ] Env" in captured.out
    assert "packages" in captured.out


def test_print_text_report_non_verbose(capsys) -> None:
    sections = [diagnostics.Section("Env", "ok", "ready", {"packages": {"numpy": "1.0"}})]

    diagnostics._print_text_report(sections, verbose=False)
    captured = capsys.readouterr()

    assert "[OK     ] Env" in captured.out
    assert "packages" not in captured.out