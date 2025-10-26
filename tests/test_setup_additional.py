"""Additional tests to exercise setup command branches."""

from __future__ import annotations

import logging
from argparse import Namespace
from pathlib import Path

import pytest

from nesdr_igate import config as config_module
from nesdr_igate.commands import setup
from nesdr_igate.config import StationConfig, save_config


def _setup_caplog(caplog, level=logging.INFO) -> None:
    caplog.set_level(level, logger="nesdr_igate.commands.setup")
    caplog.clear()


def test_run_setup_reset_removes_config(tmp_path: Path, monkeypatch, caplog) -> None:
    _setup_caplog(caplog)
    config_path = tmp_path / "config.toml"

    monkeypatch.setattr(
        config_module, "_store_passcode_in_keyring", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        config_module, "_retrieve_passcode_from_keyring", lambda *_: "12345"
    )
    delete_calls: list[str] = []
    monkeypatch.setattr(
        config_module,
        "delete_passcode_from_keyring",
        lambda callsign: delete_calls.append(callsign),
    )

    cfg = StationConfig(
        callsign="N0CALL-10", passcode="12345", passcode_in_keyring=True
    )
    save_config(cfg, path=config_path)

    args = Namespace(
        config=str(config_path), reset=True, non_interactive=True, dry_run=False
    )
    exit_code = setup.run_setup(args)

    assert exit_code == 1
    assert "Removed existing configuration" in caplog.text
    assert config_path.exists() is False
    assert delete_calls == ["N0CALL-10"]


def test_interactive_prompt_keyring_store(monkeypatch) -> None:
    responses = iter(
        [
            "n0test-1",  # callsign
            "y",  # store in keyring
            "custom.aprs.net",  # aprs server
            "14580",  # aprs port
            "30.5",  # latitude
            "-97.7",  # longitude
            "Beacon",  # comment
            "192.0.2.1",  # kiss host
            "9001",  # kiss port
        ]
    )
    passwords = iter(["pass123", "pass123"])

    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    monkeypatch.setattr(setup, "getpass", lambda _: next(passwords))
    monkeypatch.setattr(setup.config_module, "keyring_supported", lambda: True)
    store_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        setup.config_module,
        "store_passcode_in_keyring",
        lambda callsign, passcode: store_calls.append((callsign, passcode)),
    )
    monkeypatch.setattr(
        setup.config_module, "delete_passcode_from_keyring", lambda *_: None
    )

    config = setup._interactive_prompt(None)

    assert config.callsign == "N0TEST-1"
    assert config.passcode == "pass123"
    assert config.passcode_in_keyring is True
    assert config.latitude == pytest.approx(30.5)
    assert config.longitude == pytest.approx(-97.7)
    assert config.kiss_port == 9001
    assert store_calls == [("N0TEST-1", "pass123")]


def test_interactive_prompt_keyring_missing_backend(monkeypatch, caplog) -> None:
    _setup_caplog(caplog)
    existing = StationConfig(
        callsign="N0DEV-2",
        passcode="secret",
        passcode_in_keyring=True,
        aprs_server="existing.aprs",
        aprs_port=12345,
        kiss_host="127.0.0.1",
        kiss_port=9100,
    )

    responses = iter(["", "", "", "", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    monkeypatch.setattr(setup, "getpass", lambda _: "")
    monkeypatch.setattr(setup.config_module, "keyring_supported", lambda: False)
    monkeypatch.setattr(
        setup.config_module, "delete_passcode_from_keyring", lambda *_: None
    )

    config = setup._interactive_prompt(existing)
    assert "keyring backend is unavailable" in caplog.text
    assert config.passcode_in_keyring is False
    assert config.passcode == "secret"
    assert config.callsign == "N0DEV-2"


def test_prompt_yes_no_with_invalid_response(monkeypatch, caplog) -> None:
    _setup_caplog(caplog, level=logging.WARNING)
    responses = iter(["maybe", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))

    result = setup._prompt_yes_no("Continue?", default=True)
    assert result is True
    assert "Please answer 'y' or 'n'" in caplog.text


def test_maybe_render_direwolf_config_template_missing(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    _setup_caplog(caplog)
    monkeypatch.setattr(setup, "_load_direwolf_template", lambda: None)
    cfg = StationConfig(callsign="N0CALL-1", passcode="12345")

    setup._maybe_render_direwolf_config(cfg, tmp_path)
    assert "Direwolf template unavailable" in caplog.text
    assert not (tmp_path / "direwolf.conf").exists()


def test_maybe_render_direwolf_config_existing_decline(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    _setup_caplog(caplog)
    monkeypatch.setattr(
        setup, "_load_direwolf_template", lambda: "CALLSIGN {{{CALLSIGN}}}"
    )
    cfg = StationConfig(
        callsign="N0CALL-1", passcode="12345", aprs_server="example", aprs_port=12345
    )
    dest = tmp_path / "direwolf.conf"
    dest.write_text("existing", encoding="utf-8")
    monkeypatch.setattr(setup.config_module, "get_data_dir", lambda: tmp_path / "data")

    prompts: list[str] = []
    monkeypatch.setattr(
        setup,
        "_prompt_yes_no",
        lambda message, default: prompts.append(message) or False,
    )

    setup._maybe_render_direwolf_config(cfg, tmp_path)

    assert "Keeping existing" in caplog.text
    assert dest.read_text(encoding="utf-8") == "existing"
    assert prompts and "Overwrite existing" in prompts[0]


def test_run_hardware_validation_reports(monkeypatch, caplog) -> None:
    _setup_caplog(caplog)
    which_calls: list[str] = []

    def fake_which(command: str) -> str | None:
        which_calls.append(command)
        mapping = {
            "rtl_fm": "/usr/bin/rtl_fm",
            "rtl_test": "/usr/bin/rtl_test",
            "direwolf": None,
        }
        return mapping.get(command)

    class DummyRunResult:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = "Average offset -1.2 ppm after 10 seconds"
            self.stderr = ""

    def fake_probe(host: str, port: int, timeout: float):  # type: ignore[no-untyped-def]
        if host == "127.0.0.1":
            return type(
                "Result", (), {"success": True, "latency_ms": 12.3, "error": None}
            )()
        return type(
            "Result", (), {"success": False, "latency_ms": None, "error": "timeout"}
        )()

    monkeypatch.setattr(setup.shutil, "which", fake_which)
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: DummyRunResult())
    monkeypatch.setattr(setup, "probe_tcp_endpoint", fake_probe)
    monkeypatch.setattr(setup, "_report_direwolf_log_summary", lambda: None)
    monkeypatch.setattr(setup, "_can_launch_direwolf", lambda: True)
    launch_calls: list[StationConfig] = []
    monkeypatch.setattr(
        setup, "_launch_direwolf_probe", lambda cfg: launch_calls.append(cfg)
    )
    prompt_calls: list[str] = []
    monkeypatch.setattr(
        setup,
        "_prompt_yes_no",
        lambda message, default: prompt_calls.append(message) or False,
    )

    cfg = StationConfig(
        callsign="N0CALL-1",
        passcode="12345",
        aprs_server="aprs.example",
        aprs_port=14580,
        kiss_host="127.0.0.1",
        kiss_port=9001,
    )

    setup._run_hardware_validation(cfg)

    assert "rtl_test: ppm offset" in caplog.text
    assert "KISS: reachable" in caplog.text
    assert "APRS-IS: unable" in caplog.text
    assert "Launch Direwolf" in prompt_calls[0]
    assert launch_calls == []
    assert set(which_calls) == {"rtl_fm", "rtl_test", "direwolf"}


def test_run_hardware_validation_launches_probe(monkeypatch, caplog) -> None:
    _setup_caplog(caplog)
    monkeypatch.setattr(setup.shutil, "which", lambda command: "/usr/bin/" + command)
    monkeypatch.setattr(
        setup,
        "probe_tcp_endpoint",
        lambda *_, **__: type(
            "Result", (), {"success": True, "latency_ms": 1.0, "error": None}
        )(),
    )
    monkeypatch.setattr(setup, "_report_direwolf_log_summary", lambda: None)
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *a, **k: type(
            "Result", (), {"returncode": 1, "stdout": "", "stderr": "boom"}
        )(),
    )
    launch_calls: list[StationConfig] = []
    monkeypatch.setattr(
        setup, "_launch_direwolf_probe", lambda cfg: launch_calls.append(cfg)
    )

    prompts = iter([True])
    monkeypatch.setattr(setup, "_prompt_yes_no", lambda message, default: next(prompts))
    monkeypatch.setattr(setup, "_can_launch_direwolf", lambda: True)

    cfg = StationConfig(
        callsign="N0CALL-1",
        passcode="12345",
        aprs_server="aprs",
        aprs_port=14580,
        kiss_host="127.0.0.1",
        kiss_port=9001,
    )

    setup._run_hardware_validation(cfg)

    assert "rtl_test exit code" in caplog.text
    assert launch_calls == [cfg]
