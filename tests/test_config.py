"""Tests for configuration helpers."""

from __future__ import annotations

from neo_rx import config as config_module
from neo_rx.config import StationConfig


def test_save_and_load_roundtrip(tmp_path) -> None:
    cfg = StationConfig(
        callsign="N0CALL-10",
        passcode="12345",
        aprs_server="noam.aprs2.net",
        aprs_port=14580,
        latitude=12.34,
        longitude=-56.78,
        beacon_comment="Testing",
        kiss_host="127.0.0.1",
        kiss_port=8001,
        center_frequency_hz=144_390_000.0,
        sample_rate_sps=250_000.0,
        gain="auto",
        ppm_correction=2,
    )

    path = tmp_path / "config.toml"
    config_module.save_config(cfg, path=path)

    loaded = config_module.load_config(path)

    assert loaded == cfg


def test_resolve_config_path_env_override(monkeypatch, tmp_path) -> None:
    path = tmp_path / "custom.toml"
    monkeypatch.setenv(config_module.CONFIG_ENV_VAR, str(path))

    resolved = config_module.resolve_config_path()

    assert resolved == path


def test_resolve_config_path_legacy_env(monkeypatch, tmp_path) -> None:
    # Ensure the modern override is absent so the legacy variable is used.
    monkeypatch.delenv(config_module.CONFIG_ENV_VAR, raising=False)
    legacy_path = tmp_path / "legacy.toml"
    monkeypatch.setenv(config_module.LEGACY_CONFIG_ENV_VAR, str(legacy_path))

    resolved = config_module.resolve_config_path()

    assert resolved == legacy_path


def test_get_config_dir_prefers_existing_legacy(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    legacy_dir = tmp_path / config_module.LEGACY_CONFIG_DIR_NAME
    legacy_dir.mkdir(parents=True, exist_ok=True)

    resolved = config_module.get_config_dir()

    assert resolved == legacy_dir
