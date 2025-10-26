"""Tests for configuration helpers."""

from __future__ import annotations

from nesdr_igate import config as config_module
from nesdr_igate.config import StationConfig


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
