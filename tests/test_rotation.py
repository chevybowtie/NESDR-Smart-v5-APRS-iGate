"""Tests for shared weekly log/data rotation helpers (HARDENING.md #5-7)."""

from __future__ import annotations

import logging.handlers
from pathlib import Path

from neo_core.rotation import (
    DEFAULT_RETENTION_WEEKS,
    RotatingJsonlWriter,
    build_weekly_rotating_handler,
    resolve_retention_weeks,
)

ENV_VAR = "NEO_RX_TEST_RETENTION_WEEKS"


def test_resolve_retention_weeks_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert resolve_retention_weeks(ENV_VAR) == DEFAULT_RETENTION_WEEKS


def test_resolve_retention_weeks_honors_override(monkeypatch) -> None:
    monkeypatch.setenv(ENV_VAR, "4")
    assert resolve_retention_weeks(ENV_VAR) == 4


def test_resolve_retention_weeks_falls_back_on_invalid_value(monkeypatch) -> None:
    monkeypatch.setenv(ENV_VAR, "not-a-number")
    assert resolve_retention_weeks(ENV_VAR) == DEFAULT_RETENTION_WEEKS


def test_resolve_retention_weeks_falls_back_on_non_positive_value(monkeypatch) -> None:
    monkeypatch.setenv(ENV_VAR, "0")
    assert resolve_retention_weeks(ENV_VAR) == DEFAULT_RETENTION_WEEKS
    monkeypatch.setenv(ENV_VAR, "-3")
    assert resolve_retention_weeks(ENV_VAR) == DEFAULT_RETENTION_WEEKS


def test_build_weekly_rotating_handler_configures_weekly_rollover(tmp_path: Path) -> None:
    handler = build_weekly_rotating_handler(tmp_path / "test.log", retention_weeks=12)
    try:
        assert isinstance(handler, logging.handlers.TimedRotatingFileHandler)
        assert handler.when == "W0"
        assert handler.backupCount == 12
        assert handler.utc is True
    finally:
        handler.close()


def test_rotating_jsonl_writer_appends_lines(tmp_path: Path) -> None:
    path = tmp_path / "data.jsonl"
    writer = RotatingJsonlWriter(path, retention_env_var=ENV_VAR)
    try:
        writer.write_line('{"a": 1}')
        writer.write_line('{"a": 2}')
    finally:
        writer.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == ['{"a": 1}', '{"a": 2}']


def test_rotating_jsonl_writer_retention_weeks_reads_env_var(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_VAR, "6")
    writer = RotatingJsonlWriter(tmp_path / "data.jsonl", retention_env_var=ENV_VAR)
    try:
        assert writer.retention_weeks == 6
        assert writer._handler.backupCount == 6
    finally:
        writer.close()


def test_rotating_jsonl_writer_default_retention_is_twelve_weeks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    writer = RotatingJsonlWriter(tmp_path / "data.jsonl", retention_env_var=ENV_VAR)
    try:
        assert writer.retention_weeks == 12
    finally:
        writer.close()
