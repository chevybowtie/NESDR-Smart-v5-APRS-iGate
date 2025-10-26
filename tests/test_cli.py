"""Tests for the CLI entry points."""

from __future__ import annotations

import json
from collections.abc import Iterator

from nesdr_igate.cli import main
from nesdr_igate.config import CONFIG_ENV_VAR, StationConfig, save_config


def test_setup_non_interactive(tmp_path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    cfg = StationConfig(callsign="N0CALL-10", passcode="12345", latitude=12.34, longitude=-56.78)
    save_config(cfg, path=config_path)
    monkeypatch.setenv("NESDR_IGATE_CONFIG_PATH", str(config_path))

    exit_code = main(["setup", "--non-interactive"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Configuration OK" in captured.out
    assert "N0CALL-10" in captured.out


def test_setup_dry_run_interactive(tmp_path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("NESDR_IGATE_CONFIG_PATH", str(config_path))

    inputs: Iterator[str] = iter([
        "N0CALL-10",  # callsign
        "",  # aprs server default
        "",  # aprs port default
        "",  # latitude
        "",  # longitude
        "",  # beacon comment
        "",  # kiss host default
        "",  # kiss port default
    ])
    passwords: Iterator[str] = iter(["12345", "12345"])

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("nesdr_igate.commands.setup.getpass", lambda _: next(passwords))

    exit_code = main(["setup", "--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Dry run" in captured.out
    assert not config_path.exists()


def test_setup_writes_direwolf_config(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("NESDR_IGATE_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))

    inputs: Iterator[str] = iter([
        "KJ5EVH-10",  # callsign
        "custom.aprs.net",  # aprs server
        "14580",  # aprs port
        "30.123456",  # latitude
        "-97.987654",  # longitude
        "Test beacon comment",  # beacon comment
        "192.0.2.5",  # kiss host
        "9001",  # kiss port
        "",  # accept default yes for direwolf config render
    ])
    passwords: Iterator[str] = iter(["s3cret", "s3cret"])

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("nesdr_igate.commands.setup.getpass", lambda _: next(passwords))

    exit_code = main(["setup"])

    assert exit_code == 0
    assert config_path.exists()

    direwolf_path = config_path.parent / "direwolf.conf"
    assert direwolf_path.exists()

    text = direwolf_path.read_text(encoding="utf-8")
    expected_log_dir = tmp_path / "xdg_data" / "nesdr-igate" / "logs"

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

    from nesdr_igate.aprs.kiss_client import KISSFrame

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
            return KISSFrame(port=0, command=0, payload=b"TEST")

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

    monkeypatch.setattr("nesdr_igate.commands.listen.RtlFmAudioCapture", DummyCapture)
    monkeypatch.setattr("nesdr_igate.commands.listen.subprocess.Popen", lambda *a, **k: DummyProcess())
    monkeypatch.setattr("nesdr_igate.commands.listen.KISSClient", DummyKISSClient)
    monkeypatch.setattr("nesdr_igate.commands.listen.APRSISClient", DummyAPRSClient)
    monkeypatch.setattr("nesdr_igate.commands.listen.kiss_payload_to_tnc2", lambda *_: "N0CALL-10>APRS:TEST")

    exit_code = main(["listen", "--once", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Frames processed: 1" in captured.out
    assert "Connected to APRS-IS" in captured.out
    assert DummyAPRSClient.instances
    assert DummyAPRSClient.instances[0].sent_packets == ["N0CALL-10>APRS:TEST"]
    assert DummyAPRSClient.instances[0].closed is True


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

    from nesdr_igate.commands import diagnostics as diag

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

    exit_code = main(["diagnostics", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["config"]["status"] == "ok"
    assert payload["config"]["details"]["path"] == str(config_path)
    assert payload["config"]["details"]["kiss"] == "192.0.2.5:9001"
    assert "N0CALL-10" in payload["config"]["details"]["summary"]