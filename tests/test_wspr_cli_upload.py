"""CLI-level tests for the WSPR upload command guard rails."""

from argparse import Namespace

import logging

import pytest

from neo_rx.commands import wspr as wspr_cmd
from neo_rx.config import StationConfig


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
    monkeypatch.setattr(wspr_cmd, "_load_config_if_present", lambda _path: None)
    caplog.set_level(logging.ERROR)

    exit_code = wspr_cmd.run_wspr(base_args)

    assert exit_code == 1
    assert "Cannot upload WSPR spots without a configuration" in caplog.text


def test_upload_requires_uploader_enabled(monkeypatch, caplog, tmp_path, base_args):
    cfg = StationConfig(callsign="TEST", passcode="12345", wspr_uploader_enabled=False)
    monkeypatch.setattr(wspr_cmd, "_load_config_if_present", lambda _path: cfg)
    monkeypatch.setattr(wspr_cmd.config_module, "get_data_dir", lambda: tmp_path)
    caplog.set_level(logging.ERROR)

    exit_code = wspr_cmd.run_wspr(base_args)

    assert exit_code == 1
    assert "WSPR uploader is disabled" in caplog.text
