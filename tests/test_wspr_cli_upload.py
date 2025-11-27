"""CLI-level tests for the WSPR upload command guard rails."""

from argparse import Namespace

import logging

import pytest

from neo_wspr.commands import run_upload
from neo_core.config import StationConfig
from neo_core import config as config_module


@pytest.fixture(name="base_args")
def _base_args():
    return Namespace(
        upload=True,
        heartbeat=False,
        json=False,
        scan=False,
        diagnostics=False,
        calibrate=False,
        start=False,
        mqtt=None,
        band=None,
        keep_temp=False,
        config=None,
    )


def test_upload_requires_configuration(monkeypatch, caplog, base_args):
    monkeypatch.setattr(config_module, "load_config", lambda path=None: (_ for _ in ()).throw(Exception("No config")))
    caplog.set_level(logging.ERROR)

    exit_code = run_upload(base_args)

    assert exit_code == 1
    assert "Cannot upload WSPR spots without a configuration" in caplog.text


def test_upload_requires_uploader_enabled(monkeypatch, caplog, tmp_path, base_args):
    cfg = StationConfig(callsign="TEST", passcode="12345", wspr_uploader_enabled=False)
    monkeypatch.setattr(config_module, "load_config", lambda path=None: cfg)
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)
    caplog.set_level(logging.ERROR)

    exit_code = run_upload(base_args)

    assert exit_code == 1
    assert "WSPR uploader is disabled" in caplog.text
