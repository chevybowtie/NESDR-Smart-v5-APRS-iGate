"""Tests for JSON output formatting in WSPR CLI."""

import json
from argparse import Namespace

import pytest

from neo_igate.commands import wspr as wspr_cmd
from neo_igate import config as config_module


def test_scan_json_output(monkeypatch, capsys):
    """Test --scan --json produces valid JSON report."""
    cfg = config_module.StationConfig(
        callsign="TEST",
        passcode="12345",
        wspr_bands_hz=[14080000, 7080000],
        wspr_capture_duration_s=10,
    )
    monkeypatch.setattr(config_module, "load_config", lambda path=None: cfg)

    def fake_scan_bands(bands, capture_fn, duration_s):
        """Mock scan_bands that ignores capture_fn and returns canned reports."""
        return [
            {
                "band_hz": 14080000,
                "band_decodes": 2,
                "decodes_per_min": 12.0,
                "median_snr_db": -11,
                "max_snr_db": -10,
                "unique_calls": 2,
            },
            {
                "band_hz": 7080000,
                "band_decodes": 0,
                "decodes_per_min": 0.0,
                "median_snr_db": None,
                "max_snr_db": None,
                "unique_calls": 0,
            },
        ]

    monkeypatch.setattr(wspr_cmd.wspr_scan, "scan_bands", fake_scan_bands)

    args = Namespace(
        scan=True,
        json=True,
        config=None,
        start=False,
        diagnostics=False,
        calibrate=False,
        upload=False,
        mqtt=None,
    )

    result = wspr_cmd.run_wspr(args)
    assert result == 0

    captured = capsys.readouterr()
    output = captured.out.strip()
    
    # Verify valid JSON with expected structure
    data = json.loads(output)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["band_hz"] == 14080000
    assert data[0]["band_decodes"] == 2
    assert data[1]["band_hz"] == 7080000


def test_upload_json_output(monkeypatch, capsys, tmp_path):
    """Test --upload --json produces drain result in JSON."""
    # Enqueue some spots
    queue_file = tmp_path / "queue.jsonl"
    uploader = wspr_cmd.WsprUploader(queue_path=queue_file)
    uploader.enqueue_spot({"call": "K1ABC", "freq_hz": 14080000})
    uploader.enqueue_spot({"call": "K2DEF", "freq_hz": 14080100})

    # Mock the uploader to succeed on all
    monkeypatch.setattr(uploader, "upload_spot", lambda spot: True)

    # Patch the factory to return our uploader
    original_init = wspr_cmd.WsprUploader.__init__

    def mock_init(self, *args, **kwargs):
        self.queue_path = queue_file
        self.credentials = {}

    monkeypatch.setattr(wspr_cmd.WsprUploader, "__init__", mock_init)

    args = Namespace(
        upload=True,
        json=True,
        config=None,
        start=False,
        scan=False,
        diagnostics=False,
        calibrate=False,
        mqtt=None,
    )

    result = wspr_cmd.run_wspr(args)
    assert result == 0

    captured = capsys.readouterr()
    output = captured.out.strip()

    # Verify valid JSON with drain metrics
    data = json.loads(output)
    assert data["attempted"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0
