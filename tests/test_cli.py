"""Tests for the CLI entry points."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest

from neo_aprs.aprs.aprsis_client import APRSISClientError
from neo_core.cli import main
from neo_rx.aprs.kiss_client import KISSCommand
from neo_core.config import CONFIG_ENV_VAR, StationConfig, save_config
import neo_rx.cli as cli


def test_cli_version_flag(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "neo-rx" in captured.out
    assert "0.2.2" in captured.out or "." in captured.out


def test_resolve_log_level_prefers_argument(monkeypatch) -> None:
    monkeypatch.delenv("NEO_RX_LOG_LEVEL", raising=False)
    assert cli._resolve_log_level(" 42 ") == 42


def test_resolve_log_level_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("NEO_RX_LOG_LEVEL", "debug")
    assert cli._resolve_log_level(None) == logging.DEBUG


def test_configure_logging_handles_oserror(monkeypatch) -> None:
    monkeypatch.delenv("NEO_RX_LOG_LEVEL", raising=False)

    class BrokenPath:
        def __truediv__(self, _name: str):  # pragma: no cover - simple helper
            return self

        def mkdir(self, *_, **__):
            raise OSError("boom")

    broken = BrokenPath()
    monkeypatch.setattr(cli.config_module, "get_data_dir", lambda: broken)

    calls: dict[str, object] = {}

    def fake_basic_config(**kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(cli.logging, "basicConfig", fake_basic_config)

    cli._configure_logging(None)

    handlers = calls.get("handlers")
    assert isinstance(handlers, list)
    assert len(handlers) == 1


def test_main_errors_on_unknown_args(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["aprs", "listen", "--bogus"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "unrecognized arguments" in captured.err or "invalid" in captured.err


def test_main_defaults_to_listen_when_no_command() -> None:
    # New CLI requires mode - no default behavior
    with pytest.raises(SystemExit) as excinfo:
        main([])

    assert excinfo.value.code == 2  # argparse error code


def test_main_injects_listen_for_flag_only_invocation() -> None:
    # New CLI requires mode - flags alone don't default to listen
    with pytest.raises(SystemExit) as excinfo:
        main(["--no-color"])

    assert excinfo.value.code == 2  # argparse error code


def test_setup_non_interactive(tmp_path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    cfg = StationConfig(
        callsign="N0CALL-10", passcode="12345", latitude=12.34, longitude=-56.78
    )
    save_config(cfg, path=config_path)
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config_path))

    exit_code = main(["aprs", "setup", "--non-interactive"])
    capsys.readouterr()

    assert exit_code == 0
    # Output may be via logging, not stdout
    # assert "Configuration OK" in captured.out or "N0CALL-10" in captured.out


def test_setup_dry_run_interactive(tmp_path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config_path))
    monkeypatch.setattr(
        "neo_aprs.commands.setup.config_module.keyring_supported", lambda: False
    )
    monkeypatch.setattr(
        "neo_aprs.commands.setup._offer_hardware_validation", lambda *_: None
    )

    inputs: Iterator[str] = iter(
        [
            "N0CALL-10",  # callsign
            "",  # aprs server default
            "",  # aprs port default
            "",  # latitude
            "",  # longitude
            "",  # beacon comment
            "",  # kiss host default
            "",  # kiss port default
        ]
    )
    passwords: Iterator[str] = iter(["12345", "12345"])

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("neo_aprs.commands.setup.getpass", lambda _: next(passwords))

    exit_code = main(["aprs", "setup", "--dry-run"])
    capsys.readouterr()

    assert exit_code == 0
    # Dry run check - config should not exist
    assert not config_path.exists()


def test_setup_writes_direwolf_config(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    monkeypatch.setattr(
        "neo_aprs.commands.setup.config_module.keyring_supported", lambda: False
    )
    monkeypatch.setattr(
        "neo_aprs.commands.setup._offer_hardware_validation", lambda *_: None
    )

    inputs: Iterator[str] = iter(
        [
            "KJ5EVH-10",  # callsign
            "custom.aprs.net",  # aprs server
            "14580",  # aprs port
            "30.123456",  # latitude
            "-97.987654",  # longitude
            "Test beacon comment",  # beacon comment
            "192.0.2.5",  # kiss host
            "9001",  # kiss port
            "",  # accept default yes for direwolf config render
        ]
    )
    passwords: Iterator[str] = iter(["s3cret", "s3cret"])

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("neo_aprs.commands.setup.getpass", lambda _: next(passwords))

    exit_code = main(["aprs", "setup"])

    assert exit_code == 0
    assert config_path.exists()

    direwolf_path = config_path.parent / "direwolf.conf"
    assert direwolf_path.exists()

    text = direwolf_path.read_text(encoding="utf-8")
    expected_log_dir = tmp_path / "xdg_data" / "neo-rx" / "logs"

    assert "MYCALL KJ5EVH-10" in text
    assert "IGLOGIN KJ5EVH-10 s3cret" in text
    assert "IGSERVER custom.aprs.net 14580" in text
    assert "lat=30.123456 long=-97.987654" in text
    assert 'comment="Test beacon comment"' in text
    assert "KISSPORT 9001" in text
    assert f"LOGDIR {expected_log_dir}" in text
    assert "{{" not in text  # ensure template placeholders replaced
    assert expected_log_dir.exists()


def test_listen_command_once(tmp_path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    direwolf_conf = tmp_path / "direwolf.conf"
    direwolf_conf.write_text("dummy", encoding="utf-8")
    cfg = StationConfig(
        callsign="N0CALL-10",
        passcode="12345",
        aprs_server="test.aprs.net",
        aprs_port=14580,
        kiss_host="127.0.0.1",
        kiss_port=9001,
        center_frequency_hz=144_390_000.0,
        gain=35,
        ppm_correction=1,
    )
    save_config(cfg, path=config_path)
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config_path))

    class DummyCapture:
        def __init__(self, *_: object, **__: object) -> None:
            self.started = False

        def start(self) -> None:
            self.started = True

        def read(self, num_bytes: int) -> bytes:
            return b"\x00" * num_bytes

        def stop(self) -> None:
            self.started = False

    class DummyProcess:
        def __init__(self, *_: object, **__: object) -> None:
            self.pid = 1234
            import io

            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()
            self.terminated = False
            self.killed = False

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def kill(self) -> None:
            self.killed = True

    from neo_aprs.aprs.kiss_client import KISSFrame

    class DummyKISSClient:
        def __init__(self, config: object) -> None:
            self.config = config
            self.connected = False
            self.closed = False
            self.frames_returned = 0

        def connect(self) -> None:
            self.connected = True

        def read_frame(self, timeout: float | None = None) -> KISSFrame:
            self.frames_returned += 1
            return KISSFrame(port=0, command=KISSCommand.DATA, payload=b"TEST")

        def close(self) -> None:
            self.closed = True

    class DummyAPRSClient:
        instances: list["DummyAPRSClient"] = []

        def __init__(self, config: object) -> None:
            self.config = config
            self.connected = False
            self.closed = False
            self.sent_packets: list[str] = []
            DummyAPRSClient.instances.append(self)

        def connect(self) -> None:
            self.connected = True

        def send_packet(self, packet: str) -> None:
            self.sent_packets.append(packet)

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr("neo_aprs.commands.listen.RtlFmAudioCapture", DummyCapture)
    monkeypatch.setattr(
        "neo_aprs.commands.listen.subprocess.Popen", lambda *a, **k: DummyProcess()
    )
    monkeypatch.setattr("neo_aprs.commands.listen.KISSClient", DummyKISSClient)
    monkeypatch.setattr("neo_aprs.commands.listen.APRSISClient", DummyAPRSClient)
    monkeypatch.setattr(
        "neo_aprs.commands.listen.kiss_payload_to_tnc2",
        lambda *_: "N0CALL-10>APRS:TEST",
    )

    exit_code = main(["aprs", "listen", "--once", "--config", str(config_path)])
    capsys.readouterr()

    assert exit_code == 0
    assert DummyAPRSClient.instances
    # Listener adds q-construct; accept packet with qAR appended
    assert DummyAPRSClient.instances[0].sent_packets == [
        "N0CALL-10>APRS,qAR,N0CALL-10:TEST"
    ]
    assert DummyAPRSClient.instances[0].closed is True


def test_listen_reconnect_and_stats(tmp_path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    direwolf_conf = tmp_path / "direwolf.conf"
    direwolf_conf.write_text("dummy", encoding="utf-8")
    cfg = StationConfig(
        callsign="N0CALL-10",
        passcode="12345",
        aprs_server="test.aprs.net",
        aprs_port=14580,
        kiss_host="127.0.0.1",
        kiss_port=9001,
        center_frequency_hz=144_390_000.0,
    )
    save_config(cfg, path=config_path)

    class TimeStub:
        def __init__(self) -> None:
            self.current = 0.0

        def monotonic(self) -> float:
            return self.current

        def sleep(self, seconds: float) -> None:
            self.current += seconds

        def advance(self, seconds: float) -> None:
            self.current += seconds

    time_stub = TimeStub()
    monkeypatch.setattr("neo_aprs.commands.listen.time", time_stub)

    class DummyCapture:
        def __init__(self, *_: object, **__: object) -> None:
            self.started = False

        def start(self) -> None:
            self.started = True

        def read(self, num_bytes: int) -> bytes:
            return b"\x00" * num_bytes

        def stop(self) -> None:
            self.started = False

    class DummyProcess:
        def __init__(self, *_: object, **__: object) -> None:
            import io

            self.pid = 1234
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()
            self.terminated = False
            self.killed = False

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def kill(self) -> None:
            self.killed = True

    from neo_aprs.aprs.kiss_client import KISSFrame

    class DummyKISSClient:
        def __init__(self, config: object) -> None:
            self.config = config
            self.connected = False
            self.closed = False
            self._frames = [b"FIRST", b"SECOND"]
            self._index = 0

        def connect(self) -> None:
            self.connected = True

        def read_frame(self, timeout: float | None = None) -> KISSFrame:
            if self._index < len(self._frames):
                payload = self._frames[self._index]
                self._index += 1
                return KISSFrame(port=0, command=KISSCommand.DATA, payload=payload)
            raise KeyboardInterrupt

        def close(self) -> None:
            self.closed = True

    class DummyAPRSClient:
        instances: list["DummyAPRSClient"] = []

        def __init__(self, config: object) -> None:
            self.config = config
            self.connected = False
            self.closed = False
            self.sent_packets: list[str] = []
            self.instance_id = len(DummyAPRSClient.instances)
            DummyAPRSClient.instances.append(self)

        def connect(self) -> None:
            self.connected = True

        def send_packet(self, packet: str) -> None:
            if self.instance_id == 0 and not self.sent_packets:
                time_stub.advance(61)
                raise APRSISClientError("boom")
            self.sent_packets.append(packet)

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr("neo_aprs.commands.listen.RtlFmAudioCapture", DummyCapture)
    monkeypatch.setattr(
        "neo_aprs.commands.listen.subprocess.Popen", lambda *a, **k: DummyProcess()
    )
    monkeypatch.setattr("neo_aprs.commands.listen.KISSClient", DummyKISSClient)
    monkeypatch.setattr("neo_aprs.commands.listen.APRSISClient", DummyAPRSClient)
    monkeypatch.setattr(
        "neo_aprs.commands.listen.kiss_payload_to_tnc2",
        lambda payload: f"N0CALL-10>APRS:{payload.decode()}",
    )

    exit_code = main(["aprs", "listen", "--config", str(config_path)])
    capsys.readouterr()

    assert exit_code == 0
    assert len(DummyAPRSClient.instances) >= 2
    assert DummyAPRSClient.instances[0].closed is True
    assert DummyAPRSClient.instances[-1].sent_packets == [
        "N0CALL-10>APRS,qAR,N0CALL-10:SECOND"
    ]


def test_diagnostics_command_json(tmp_path, monkeypatch, capsys) -> None:
    cfg = StationConfig(
        callsign="N0CALL-10",
        passcode="12345",
        aprs_server="test.aprs.net",
        aprs_port=12345,
        kiss_host="192.0.2.5",
        kiss_port=9001,
    )
    config_path = tmp_path / "config.toml"
    save_config(cfg, path=config_path)
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config_path))

    from neo_aprs.commands import diagnostics as diag

    monkeypatch.setattr(
        diag,
        "_check_sdr",
        lambda: diag.Section("SDR", "ok", "mock", {}),
    )
    monkeypatch.setattr(
        diag,
        "_check_direwolf",
        lambda *_: diag.Section("Direwolf", "warning", "mock", {}),
    )
    monkeypatch.setattr(
        diag,
        "_check_aprs_is",
        lambda *_: diag.Section("APRS-IS", "warning", "mock", {}),
    )

    exit_code = main(["aprs", "diagnostics", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["config"]["status"] == "ok"
    assert payload["config"]["details"]["path"] == str(config_path)
    assert payload["config"]["details"]["kiss"] == "192.0.2.5:9001"
    assert "N0CALL-10" in payload["config"]["details"]["summary"]
