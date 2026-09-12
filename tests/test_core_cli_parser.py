from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import pytest

from neo_core.cli import LOG_RETENTION_ENV_VAR, build_parser, main


def test_aprs_listen_defaults() -> None:
    args = build_parser().parse_args(["aprs", "listen"])

    assert args.mode == "aprs"
    assert args.verb == "listen"
    assert args.kiss_host == "127.0.0.1"
    assert args.kiss_port == 8001
    assert args.once is False
    assert args.no_aprsis is False
    assert args.frequency_hz is None


def test_aprs_listen_accepts_receive_only_frequency_and_common_flags() -> None:
    args = build_parser().parse_args(
        [
            "aprs",
            "listen",
            "--frequency-hz",
            "146520000",
            "--no-aprsis",
            "--once",
            "--kiss-host",
            "192.0.2.10",
            "--kiss-port",
            "9001",
            "--device-id",
            "67411606",
            "--instance-id",
            "repeater-test",
            "--config",
            "/tmp/config.toml",
            "--data-dir",
            "/tmp/data",
            "--log-level",
            "debug",
            "--no-color",
        ]
    )

    assert args.frequency_hz == 146520000.0
    assert args.no_aprsis is True
    assert args.once is True
    assert args.kiss_host == "192.0.2.10"
    assert args.kiss_port == 9001
    assert args.device_id == "67411606"
    assert args.instance_id == "repeater-test"
    assert args.config == "/tmp/config.toml"
    assert args.data_dir == "/tmp/data"
    assert args.log_level == "debug"
    assert args.no_color is True


def test_aprs_setup_parses_setup_modes() -> None:
    args = build_parser().parse_args(
        ["aprs", "setup", "--reset", "--non-interactive", "--dry-run"]
    )

    assert (args.mode, args.verb) == ("aprs", "setup")
    assert args.reset is True
    assert args.non_interactive is True
    assert args.dry_run is True


def test_aprs_diagnostics_parses_endpoint_and_output_flags() -> None:
    args = build_parser().parse_args(
        [
            "aprs",
            "diagnostics",
            "--kiss-host",
            "192.0.2.11",
            "--kiss-port",
            "9002",
            "--json",
            "--verbose",
        ]
    )

    assert (args.mode, args.verb) == ("aprs", "diagnostics")
    assert args.kiss_host == "192.0.2.11"
    assert args.kiss_port == 9002
    assert args.json is True
    assert args.verbose is True


@pytest.mark.parametrize(
    ("verb", "extra"),
    [
        ("setup", []),
        ("listen", ["--band", "20m", "--duration", "30"]),
        ("scan", ["--schedule", "/tmp/schedule.toml"]),
        ("calibrate", ["--samples", "/tmp/samples.iq"]),
        ("upload", ["--input", "/tmp/spots"]),
        ("diagnostics", ["--band", "20m"]),
        ("find-devices", []),
    ],
)
def test_wspr_commands_parse(verb: str, extra: list[str]) -> None:
    args = build_parser().parse_args(["wspr", verb, *extra])

    assert args.mode == "wspr"
    assert args.verb == verb


def test_help_lists_aprs_listener_safety_and_frequency_flags(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["aprs", "listen", "--help"])

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert "--no-aprsis" in output
    assert "--frequency-hz" in output
    assert "--help" in output


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["aprs"],
        ["aprs", "listen", "--log-level", "trace"],
        ["aprs", "listen", "--frequency-hz", "not-a-number"],
    ],
)
def test_parser_rejects_incomplete_or_invalid_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(argv)

    assert excinfo.value.code == 2


def test_main_configures_weekly_rotating_log_handler(monkeypatch, tmp_path: Path) -> None:
    """HARDENING.md #7: log files rotate weekly with a configurable retention."""
    monkeypatch.setenv(LOG_RETENTION_ENV_VAR, "5")

    main(["adsb", "find-devices", "--data-dir", str(tmp_path)])

    log_file = tmp_path / "logs" / "adsb" / "neo-rx.log"
    assert log_file.exists()

    file_handlers = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.TimedRotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].when == "W0"
    assert file_handlers[0].backupCount == 5


def test_main_defaults_log_retention_to_twelve_weeks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(LOG_RETENTION_ENV_VAR, raising=False)

    main(["adsb", "find-devices", "--data-dir", str(tmp_path)])

    file_handlers = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.TimedRotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].backupCount == 12
