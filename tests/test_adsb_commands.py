from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from neo_adsb.adsb import capture as capture_module
from neo_adsb.adsb.capture import AircraftState
from neo_adsb.adsb.diagnostics import DiagnosticResult, DiagnosticsReport
from neo_adsb.commands import diagnostics, find_devices, listen, setup


@pytest.fixture(autouse=True)
def _remove_listen_file_handlers():
    yield
    root_logger = __import__("logging").getLogger()
    for handler in list(root_logger.handlers):
        if isinstance(handler, __import__("logging").FileHandler):
            root_logger.removeHandler(handler)
            handler.close()


def test_find_devices_reports_missing_rtl_test(monkeypatch, capsys) -> None:
    monkeypatch.setattr(find_devices.shutil, "which", lambda _name: None)

    result = find_devices.run_find_devices_cmd(argparse.Namespace(json=False))

    assert result == 1
    assert "rtl_test not found" in capsys.readouterr().out


def test_find_devices_prints_text_with_serial(monkeypatch, capsys) -> None:
    completed = subprocess.CompletedProcess(
        args=["rtl_test", "-t"],
        returncode=0,
        stdout="Found 1 device(s):\n",
        stderr="  0: Nooelec NESDR, SN: 67411606\n",
    )
    monkeypatch.setattr(find_devices.shutil, "which", lambda _name: "/usr/bin/rtl_test")
    monkeypatch.setattr(find_devices.subprocess, "run", lambda *args, **kwargs: completed)

    result = find_devices.run_find_devices_cmd(argparse.Namespace(json=False))

    output = capsys.readouterr().out
    assert result == 0
    assert "Found 1 RTL-SDR device(s)" in output
    assert "67411606" in output


def test_find_devices_prints_json(monkeypatch, capsys) -> None:
    completed = subprocess.CompletedProcess(
        args=["rtl_test", "-t"],
        returncode=0,
        stdout="  0: Generic RTL-SDR, SN: ABC123\n",
        stderr="",
    )
    monkeypatch.setattr(find_devices.shutil, "which", lambda _name: "rtl_test")
    monkeypatch.setattr(find_devices.subprocess, "run", lambda *args, **kwargs: completed)

    result = find_devices.run_find_devices_cmd(argparse.Namespace(json=True))

    assert result == 0
    assert json.loads(capsys.readouterr().out)["devices"][0]["serial"] == "ABC123"


@pytest.mark.parametrize(
    "exception",
    [
        subprocess.TimeoutExpired(cmd="rtl_test", timeout=10),
        subprocess.SubprocessError("failed"),
    ],
)
def test_find_devices_reports_subprocess_errors(monkeypatch, capsys, exception) -> None:
    monkeypatch.setattr(find_devices.shutil, "which", lambda _name: "rtl_test")

    def fail(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr(find_devices.subprocess, "run", fail)

    assert find_devices.run_find_devices_cmd(argparse.Namespace(json=False)) == 1
    assert "Error" in capsys.readouterr().out


def test_find_devices_reports_no_devices(monkeypatch, capsys) -> None:
    completed = subprocess.CompletedProcess(
        args=["rtl_test", "-t"],
        returncode=1,
        stdout="",
        stderr="Failed to open rtlsdr device\n",
    )
    monkeypatch.setattr(find_devices.shutil, "which", lambda _name: "rtl_test")
    monkeypatch.setattr(find_devices.subprocess, "run", lambda *args, **kwargs: completed)

    assert find_devices.run_find_devices_cmd(argparse.Namespace(json=False)) == 1
    output = capsys.readouterr().out
    assert "No RTL-SDR devices found" in output
    assert "may be in use" in output


def test_find_aircraft_json_prefers_readsb(monkeypatch) -> None:
    monkeypatch.setattr(
        listen.os.path,
        "exists",
        lambda path: path == "/run/readsb/aircraft.json",
    )

    assert listen._find_aircraft_json() == "/run/readsb/aircraft.json"


def test_find_aircraft_json_falls_back_to_readsb(monkeypatch) -> None:
    monkeypatch.setattr(listen.os.path, "exists", lambda _path: False)

    assert listen._find_aircraft_json() == "/run/readsb/aircraft.json"


def test_display_aircraft_formats_and_limits_rows(capsys) -> None:
    aircraft = [
        AircraftState(
            hex_id="ABC123",
            flight=" TEST123 ",
            altitude_ft=30_000,
            ground_speed_kt=450.4,
            track_deg=270.2,
            latitude=39.123456,
            longitude=-96.654321,
            rssi_db=-3.4,
        ),
        AircraftState(hex_id="DEF456"),
    ]

    listen._display_aircraft(aircraft)

    output = capsys.readouterr().out
    assert "ABC123" in output
    assert "TEST123" in output
    assert "30000" in output
    assert "Total aircraft: 2" in output


def test_listen_returns_error_when_aircraft_file_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(listen.config_module, "load_config", lambda: None)
    monkeypatch.setattr(listen.config_module, "get_mode_data_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen.config_module, "get_logs_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen, "_find_aircraft_json", lambda: str(tmp_path / "missing.json"))

    result = listen.run_listen(argparse.Namespace())

    assert result == 1


def test_listen_runs_capture_processes_commands_and_stops(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    json_path = tmp_path / "aircraft.json"
    json_path.write_text('{"aircraft": []}', encoding="utf-8")
    cfg = argparse.Namespace(
        adsb_json_path=None,
        mqtt_enabled=False,
    )
    calls = []

    class FakeCapture:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))
            self.callback = None
            self.running = False

        def add_callback(self, callback):
            self.callback = callback

        def start(self):
            self.running = True
            self.callback([AircraftState(hex_id="ABC123", altitude_ft=12000)])

        def is_running(self):
            return self.running

        def stop(self):
            calls.append(("stop",))
            self.running = False

    monkeypatch.setattr(listen.config_module, "load_config", lambda *_args: cfg)
    monkeypatch.setattr(listen.config_module, "get_mode_data_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen.config_module, "get_logs_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen, "_find_aircraft_json", lambda: str(json_path))
    monkeypatch.setattr(listen, "start_keyboard_listener", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(capture_module, "AdsbCapture", FakeCapture)
    monkeypatch.setattr(
        listen,
        "process_commands",
        lambda _queue, handlers: (
            handlers["s"](),
            handlers["v"](),
            handlers["q"](),
        ),
    )
    monkeypatch.setattr(listen.threading, "Timer", lambda *_args, **_kwargs: argparse.Namespace(
        start=lambda: None
    ))

    assert listen.run_listen(argparse.Namespace(json_path=str(json_path), poll_interval=0.01)) == 0

    output = capsys.readouterr().out
    assert "ADS-B monitoring started" in output
    assert "ADS-B activity summary" in output
    assert "neo-rx" in output
    assert ("stop",) in calls
    assert calls[0][1]["json_path"] == str(json_path)


def test_listen_unique_aircraft_count_survives_lru_eviction(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """HARDENING.md #11: the seen-aircraft set is capped, but the reported
    unique-aircraft count keeps counting correctly even once eviction
    kicks in (a stale hex reappearing after eviction is counted again,
    which is the accepted tradeoff for bounded memory use)."""
    monkeypatch.setenv(listen.UNIQUE_AIRCRAFT_CAP_ENV_VAR, "2")

    json_path = tmp_path / "aircraft.json"
    json_path.write_text('{"aircraft": []}', encoding="utf-8")

    class FakeCapture:
        def __init__(self, **_kwargs):
            self.callback = None
            self.running = False

        def add_callback(self, callback):
            self.callback = callback

        def start(self):
            self.running = True
            # 4 unique sightings, but with cap=2 the LRU set can only hold
            # 2 at a time: A, B pushes A out on the third; seeing A again
            # afterward is treated as a new sighting.
            self.callback([AircraftState(hex_id="AAA111")])
            self.callback([AircraftState(hex_id="BBB222")])
            self.callback([AircraftState(hex_id="CCC333")])
            self.callback([AircraftState(hex_id="AAA111")])

        def is_running(self):
            return self.running

        def stop(self):
            self.running = False

    monkeypatch.setattr(listen.config_module, "load_config", lambda *_args: None)
    monkeypatch.setattr(listen.config_module, "get_mode_data_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen.config_module, "get_logs_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen, "_find_aircraft_json", lambda: str(json_path))
    monkeypatch.setattr(listen, "start_keyboard_listener", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(capture_module, "AdsbCapture", FakeCapture)
    monkeypatch.setattr(
        listen,
        "process_commands",
        lambda _queue, handlers: (handlers["s"](), handlers["q"]()),
    )
    monkeypatch.setattr(
        listen.threading,
        "Timer",
        lambda *_args, **_kwargs: argparse.Namespace(start=lambda: None),
    )

    assert (
        listen.run_listen(argparse.Namespace(json_path=str(json_path), poll_interval=0.01))
        == 0
    )

    output = capsys.readouterr().out
    assert "Unique aircraft seen: 4" in output


def test_listen_quiet_mode_suppresses_aircraft_display(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    json_path = tmp_path / "aircraft.json"
    json_path.write_text('{"aircraft": []}', encoding="utf-8")

    class FakeCapture:
        def __init__(self, **_kwargs):
            self.running = False

        def add_callback(self, callback):
            self.callback = callback

        def start(self):
            self.running = True
            self.callback([AircraftState(hex_id="ABC123")])

        def is_running(self):
            return self.running

        def stop(self):
            self.running = False

    monkeypatch.setattr(listen.config_module, "load_config", lambda *_args: None)
    monkeypatch.setattr(listen.config_module, "get_mode_data_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen.config_module, "get_logs_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen, "_find_aircraft_json", lambda: str(json_path))
    monkeypatch.setattr(listen, "start_keyboard_listener", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(capture_module, "AdsbCapture", FakeCapture)
    monkeypatch.setattr(
        listen, "process_commands", lambda _queue, handlers: handlers["q"]()
    )

    assert listen.run_listen(
        argparse.Namespace(json_path=str(json_path), poll_interval=0.01, quiet=True)
    ) == 0

    assert "ABC123" not in capsys.readouterr().out


def test_listen_mqtt_failure_continues_without_publisher(
    monkeypatch, tmp_path: Path, caplog
) -> None:
    import neo_rx.telemetry.mqtt_publisher  # noqa: F401
    from neo_telemetry import mqtt_publisher

    json_path = tmp_path / "aircraft.json"
    json_path.write_text('{"aircraft": []}', encoding="utf-8")
    cfg = argparse.Namespace(
        adsb_json_path=None,
        mqtt_enabled=True,
        mqtt_host="mqtt.example",
        mqtt_port=1883,
        mqtt_topic="aircraft",
    )
    captured = {}

    class FailingPublisher:
        def __init__(self, **_kwargs):
            raise RuntimeError("broker unavailable")

    class FakeCapture:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.running = False

        def add_callback(self, _callback):
            pass

        def start(self):
            self.running = True

        def is_running(self):
            return self.running

        def stop(self):
            self.running = False

    monkeypatch.setattr(listen.config_module, "load_config", lambda *_args: cfg)
    monkeypatch.setattr(listen.config_module, "get_mode_data_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen.config_module, "get_logs_dir", lambda _mode: tmp_path)
    monkeypatch.setattr(listen, "_find_aircraft_json", lambda: str(json_path))
    monkeypatch.setattr(mqtt_publisher, "MqttPublisher", FailingPublisher)
    monkeypatch.setattr(capture_module, "AdsbCapture", FakeCapture)
    monkeypatch.setattr(listen, "start_keyboard_listener", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        listen, "process_commands", lambda _queue, handlers: handlers["q"]()
    )

    assert listen.run_listen(argparse.Namespace(json_path=str(json_path))) == 0
    assert captured["publisher"] is None
    assert "Failed to create/connect publisher" in caplog.text


def test_diagnostics_text_output_includes_hints_and_verbose_details(monkeypatch, capsys) -> None:
    report = DiagnosticsReport()
    report.checks.append(
        DiagnosticResult(
            "decoder",
            "WARNING",
            "Decoder is stale",
            {"hint": "Restart readsb", "age": 42},
        )
    )
    monkeypatch.setattr(diagnostics, "run_diagnostics", lambda **_kwargs: report)

    result = diagnostics.run_diagnostics_cmd(
        argparse.Namespace(json=False, verbose=True, json_path=None)
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "decoder: " in output
    assert "Restart readsb" in output
    assert "age: 42" in output
    assert "Some warnings detected" in output


def test_diagnostics_text_output_distinguishes_errors(monkeypatch, capsys) -> None:
    report = DiagnosticsReport()
    report.checks.append(DiagnosticResult("decoder", "ERROR", "Decoder missing"))
    monkeypatch.setattr(diagnostics, "run_diagnostics", lambda **_kwargs: report)

    result = diagnostics.run_diagnostics_cmd(
        argparse.Namespace(json=False, verbose=False, json_path=None)
    )

    assert result == 1
    assert "Some checks failed" in capsys.readouterr().out


def test_setup_noninteractive_uses_defaults(monkeypatch, capsys) -> None:
    monkeypatch.setattr(setup.config_module, "load_config", lambda: None)

    result = setup.run_setup(argparse.Namespace(non_interactive=True, reset=False))

    output = capsys.readouterr().out
    assert result == 0
    assert "Non-interactive mode" in output
    assert "aircraft.json" in output


def test_setup_existing_noninteractive_config_is_kept(monkeypatch, capsys) -> None:
    existing = object()
    monkeypatch.setattr(setup.config_module, "load_config", lambda: existing)

    result = setup.run_setup(
        argparse.Namespace(non_interactive=True, reset=False, config=None)
    )

    assert result == 0
    assert "Using existing configuration" in capsys.readouterr().out
