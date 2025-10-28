"""Unit tests for diagnostics command helpers."""

from __future__ import annotations

import builtins
import json
import logging
import sys
import types
from pathlib import Path
from argparse import Namespace

from nesdr_igate.commands import diagnostics
from nesdr_igate.config import StationConfig, save_config


class _ProbeResult:
    def __init__(
        self,
        success: bool,
        *,
        latency_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        self.success = success
        self.latency_ms = latency_ms
        self.error = error


def _fake_import_factory(original):
    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "rtlsdr":
            raise ImportError("mock missing module")
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


def test_check_sdr_instantiation_fallback(monkeypatch) -> None:
    """If RtlSdr doesn't expose get_device_count, fall back to instantiation."""
    module = types.ModuleType("rtlsdr")

    class DummyRtl:
        def __init__(self, *args, **kwargs):
            # accept positional or keyword device_index
            self._idx = kwargs.get("device_index", args[0] if args else 0)

        # expose a bytes serial like some implementations
        @property
        def serial_number(self) -> bytes:
            return b"fallback-serial"

        def close(self) -> None:
            return None

    setattr(module, "RtlSdr", DummyRtl)
    monkeypatch.setitem(sys.modules, "rtlsdr", module)

    section = diagnostics._check_sdr()

    assert section.status == "ok"
    assert section.details["device_count"] == 1
    assert section.details.get("serials") == ["fallback-serial"]


def test_check_direwolf_success(monkeypatch) -> None:
    config = StationConfig(callsign="N0CALL-10", passcode="12345")

    # Simulate direwolf binary present and endpoint reachable
    monkeypatch.setattr(diagnostics, "probe_tcp_endpoint", lambda *_args, **_kwargs: _ProbeResult(True, latency_ms=12.3))
    monkeypatch.setattr(diagnostics.shutil, "which", lambda *_: "/usr/bin/direwolf")

    section = diagnostics._check_direwolf(config)

    assert section.status == "ok"
    assert section.details["latency_ms"] == 12.3


def test_check_direwolf_failure(monkeypatch) -> None:
    config = StationConfig(callsign="N0CALL-10", passcode="12345")

    # Simulate direwolf binary present but endpoint not reachable
    monkeypatch.setattr(diagnostics, "probe_tcp_endpoint", lambda *_args, **_kwargs: _ProbeResult(False, error="timeout"))
    monkeypatch.setattr(diagnostics.shutil, "which", lambda *_: "/usr/bin/direwolf")

    section = diagnostics._check_direwolf(config)

    assert section.status == "warning"
    assert section.details["error"] == "timeout"


def test_check_direwolf_no_config() -> None:
    section = diagnostics._check_direwolf(None)

    assert section.status == "warning"
    assert "Configuration unavailable" in section.message


def test_check_direwolf_not_installed(monkeypatch) -> None:
    config = StationConfig(callsign="N0CALL-10", passcode="12345")

    # Simulate direwolf binary not present
    monkeypatch.setattr(diagnostics.shutil, "which", lambda *_: None)

    section = diagnostics._check_direwolf(config)

    assert section.status == "warning"
    assert "not installed" in section.message
    assert section.details.get("installed") is False


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


def test_print_text_report_verbose(caplog) -> None:
    caplog.set_level(logging.INFO, logger="nesdr_igate.commands.diagnostics")
    caplog.clear()
    sections = [
        diagnostics.Section("Env", "ok", "ready", {"packages": {"numpy": "1.0"}})
    ]

    diagnostics._print_text_report(sections, verbose=True)
    assert "[OK     ] Env" in caplog.text
    assert "packages" in caplog.text


def test_print_text_report_non_verbose(caplog) -> None:
    caplog.set_level(logging.INFO, logger="nesdr_igate.commands.diagnostics")
    caplog.clear()
    sections = [
        diagnostics.Section("Env", "ok", "ready", {"packages": {"numpy": "1.0"}})
    ]

    diagnostics._print_text_report(sections, verbose=False)
    assert "[OK     ] Env" in caplog.text
    assert "packages" not in caplog.text


def test_run_diagnostics_json_includes_meta_and_summary(
    monkeypatch, tmp_path, capsys, caplog
) -> None:
    caplog.set_level(logging.INFO, logger="nesdr_igate.commands.diagnostics")
    caplog.clear()

    env_section = diagnostics.Section("Environment", "ok", "env", {})
    config_section = diagnostics.Section("Config", "ok", "cfg", {})
    sdr_section = diagnostics.Section("SDR", "ok", "sdr", {})
    direwolf_section = diagnostics.Section("Direwolf", "warning", "dw", {})
    aprs_section = diagnostics.Section("APRS-IS", "ok", "aprs", {})

    monkeypatch.setattr(diagnostics, "_check_environment", lambda: env_section)
    monkeypatch.setattr(
        diagnostics, "_check_config", lambda *_: (config_section, None)
    )
    monkeypatch.setattr(diagnostics, "_check_sdr", lambda: sdr_section)
    monkeypatch.setattr(
        diagnostics, "_check_direwolf", lambda *_: direwolf_section
    )
    monkeypatch.setattr(
        diagnostics, "_check_aprs_is", lambda *_: aprs_section
    )
    monkeypatch.setattr(diagnostics, "_package_version", lambda: "9.9.9")
    monkeypatch.setattr(
        diagnostics.config_module,
        "resolve_config_path",
        lambda *_: tmp_path / "config.toml",
    )

    exit_code = diagnostics.run_diagnostics(
        Namespace(config=None, json=True, verbose=False)
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["meta"]["version"] == "9.9.9"
    assert payload["summary"]["warnings"] == 1
    assert payload["summary"]["warning_sections"] == ["Direwolf"]

    summary_records = [
        record for record in caplog.records if "Diagnostics summary" in record.message
    ]
    assert summary_records == []


def test_run_diagnostics_text_emits_summary(monkeypatch, tmp_path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="nesdr_igate.commands.diagnostics")
    caplog.clear()

    env_section = diagnostics.Section("Environment", "ok", "env", {})
    config_section = diagnostics.Section("Config", "ok", "cfg", {})
    sdr_section = diagnostics.Section("SDR", "ok", "sdr", {})
    direwolf_section = diagnostics.Section("Direwolf", "warning", "dw", {})
    aprs_section = diagnostics.Section("APRS-IS", "ok", "aprs", {})

    monkeypatch.setattr(diagnostics, "_check_environment", lambda: env_section)
    monkeypatch.setattr(
        diagnostics, "_check_config", lambda *_: (config_section, None)
    )
    monkeypatch.setattr(diagnostics, "_check_sdr", lambda: sdr_section)
    monkeypatch.setattr(
        diagnostics, "_check_direwolf", lambda *_: direwolf_section
    )
    monkeypatch.setattr(
        diagnostics, "_check_aprs_is", lambda *_: aprs_section
    )
    monkeypatch.setattr(
        diagnostics.config_module,
        "resolve_config_path",
        lambda *_: tmp_path / "config.toml",
    )

    exit_code = diagnostics.run_diagnostics(
        Namespace(config=None, json=False, verbose=False)
    )

    assert exit_code == 0
    summary_records = [
        record for record in caplog.records if "Diagnostics summary" in record.message
    ]
    assert len(summary_records) == 1
    assert summary_records[0].levelno == logging.WARNING
    assert "warnings=1" in summary_records[0].message
