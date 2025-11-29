"""Tests for configuration layering."""

from __future__ import annotations

from pathlib import Path

from neo_core.config_layering import (
    load_layered_config,
    _deep_merge,
    _extract_env_overrides,
    _parse_env_value,
)


def test_load_layered_config_defaults_only(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('[station]\ncallsign = "DEFAULT"\n', encoding="utf-8")

    result = load_layered_config(config_dir=tmp_path)

    assert result == {"station": {"callsign": "DEFAULT"}}


def test_load_layered_config_mode_overrides_defaults(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('[station]\ncallsign = "DEFAULT"\n', encoding="utf-8")

    aprs_config = tmp_path / "aprs.toml"
    aprs_config.write_text('[station]\ncallsign = "APRS"\n', encoding="utf-8")

    result = load_layered_config(mode="aprs", config_dir=tmp_path)

    assert result == {"station": {"callsign": "APRS"}}


def test_load_layered_config_cli_overrides_all(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('[station]\ncallsign = "DEFAULT"\n', encoding="utf-8")

    aprs_config = tmp_path / "aprs.toml"
    aprs_config.write_text('[station]\ncallsign = "APRS"\n', encoding="utf-8")

    cli_overrides = {"station": {"callsign": "CLI"}}
    result = load_layered_config(
        mode="aprs", config_dir=tmp_path, cli_overrides=cli_overrides
    )

    assert result == {"station": {"callsign": "CLI"}}


def test_load_layered_config_merges_nested_dicts(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text(
        '[station]\ncallsign = "DEFAULT"\npasscode = "12345"\n', encoding="utf-8"
    )

    aprs_config = tmp_path / "aprs.toml"
    aprs_config.write_text('[station]\ncallsign = "APRS"\n', encoding="utf-8")

    result = load_layered_config(mode="aprs", config_dir=tmp_path)

    assert result == {"station": {"callsign": "APRS", "passcode": "12345"}}


def test_load_layered_config_missing_files_ok(tmp_path: Path) -> None:
    result = load_layered_config(mode="aprs", config_dir=tmp_path)
    assert result == {}


def test_deep_merge_replaces_scalars() -> None:
    base = {"a": 1, "b": 2}
    override = {"b": 3, "c": 4}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": 3, "c": 4}


def test_deep_merge_merges_nested_dicts() -> None:
    base = {"section": {"key1": "v1", "key2": "v2"}}
    override = {"section": {"key2": "v2_override", "key3": "v3"}}
    result = _deep_merge(base, override)
    assert result == {"section": {"key1": "v1", "key2": "v2_override", "key3": "v3"}}


def test_extract_env_overrides_top_level(monkeypatch) -> None:
    monkeypatch.setenv("NEO_RX_CALLSIGN", "TEST")
    overrides = _extract_env_overrides()
    assert overrides == {"callsign": "TEST"}


def test_extract_env_overrides_nested(monkeypatch) -> None:
    monkeypatch.setenv("NEO_RX_STATION__CALLSIGN", "TEST")
    overrides = _extract_env_overrides()
    assert overrides == {"station": {"callsign": "TEST"}}


def test_extract_env_overrides_ignores_other_vars(monkeypatch) -> None:
    monkeypatch.setenv("OTHER_VAR", "value")
    monkeypatch.setenv("NEO_RX_KEY", "value")
    overrides = _extract_env_overrides()
    assert overrides == {"key": "value"}


def test_parse_env_value_bool() -> None:
    assert _parse_env_value("true") is True
    assert _parse_env_value("TRUE") is True
    assert _parse_env_value("false") is False
    assert _parse_env_value("FALSE") is False


def test_parse_env_value_int() -> None:
    assert _parse_env_value("42") == 42
    assert _parse_env_value("-10") == -10


def test_parse_env_value_float() -> None:
    assert _parse_env_value("3.14") == 3.14
    assert _parse_env_value("-2.5") == -2.5


def test_parse_env_value_string() -> None:
    assert _parse_env_value("hello") == "hello"
    assert _parse_env_value("123abc") == "123abc"


def test_load_layered_config_env_overrides_mode(tmp_path: Path, monkeypatch) -> None:
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('[station]\ncallsign = "DEFAULT"\n', encoding="utf-8")

    aprs_config = tmp_path / "aprs.toml"
    aprs_config.write_text('[station]\ncallsign = "APRS"\n', encoding="utf-8")

    monkeypatch.setenv("NEO_RX_STATION__CALLSIGN", "ENV")

    result = load_layered_config(mode="aprs", config_dir=tmp_path)

    assert result == {"station": {"callsign": "ENV"}}
