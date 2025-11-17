"""Tests for JSON output formatting in WSPR CLI."""

import json
from argparse import Namespace


from neo_rx.commands import wspr as wspr_cmd
from neo_rx import config as config_module


def test_scan_json_output(monkeypatch, capsys, tmp_path):
    """Test --scan --json produces valid JSON report."""
    cfg = config_module.StationConfig(
        callsign="TEST",
        passcode="12345",
        wspr_bands_hz=[14080000, 7080000],
        wspr_capture_duration_s=10,
    )
    monkeypatch.setattr(config_module, "load_config", lambda path=None: cfg)
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)

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
    queue_dir = tmp_path / "wspr"
    queue_dir.mkdir(parents=True, exist_ok=True)
    queue_file = queue_dir / "wspr_upload_queue.jsonl"
    queue_file.write_text(
        '{"call":"K1ABC","freq_hz":14080000}\n{"call":"K2DEF","freq_hz":14080100}\n',
        encoding="utf-8",
    )

    cfg = config_module.StationConfig(
        callsign="TEST",
        passcode="12345",
        wspr_grid="EM12ab",
        wspr_power_dbm=37,
        wspr_uploader_enabled=True,
    )
    monkeypatch.setattr(config_module, "load_config", lambda path=None: cfg)
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)

    def mock_init(self, *args, **kwargs):
        self.queue_path = queue_file
        self.credentials = {}
        self.base_url = "https://example.com"
        self._timeout = (5, 10)

    monkeypatch.setattr(wspr_cmd.WsprUploader, "__init__", mock_init)
    monkeypatch.setattr(wspr_cmd.WsprUploader, "upload_spot", lambda self, spot: True)

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
    assert "last_error" in data
    assert data["last_error"] is None


def test_upload_json_includes_last_error(monkeypatch, capsys, tmp_path):
    cfg = config_module.StationConfig(
        callsign="TEST",
        passcode="12345",
        wspr_grid="EM12ab",
        wspr_power_dbm=37,
        wspr_uploader_enabled=True,
    )
    monkeypatch.setattr(config_module, "load_config", lambda path=None: cfg)
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)

    def mock_init(self, *args, **kwargs):
        self.queue_path = tmp_path / "wspr_queue.jsonl"
        self.credentials = {}
        self.base_url = "https://example.com"
        self._timeout = (5, 10)
        self._last_upload_error = None

    monkeypatch.setattr(wspr_cmd.WsprUploader, "__init__", mock_init)
    monkeypatch.setattr(
        wspr_cmd.WsprUploader,
        "drain",
        lambda self: {"attempted": 1, "succeeded": 0, "failed": 1, "last_error": "boom"},
    )

    args = Namespace(
        upload=True,
        json=True,
        heartbeat=False,
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
    data = json.loads(captured.out.strip())
    assert data["last_error"] == "boom"


def test_upload_sends_heartbeat_when_requested(monkeypatch, capsys, tmp_path):
    cfg = config_module.StationConfig(
        callsign="TEST",
        passcode="12345",
        wspr_grid="EM12ab",
        wspr_power_dbm=37,
        wspr_bands_hz=[14_095_600],
        wspr_capture_duration_s=119,
        wspr_uploader_enabled=True,
    )
    monkeypatch.setattr(config_module, "load_config", lambda path=None: cfg)
    monkeypatch.setattr(config_module, "get_data_dir", lambda: tmp_path)

    def mock_init(self, *args, **kwargs):
        self.queue_path = tmp_path / "wspr_queue.jsonl"
        self.credentials = {}
        self.base_url = "https://example.com"
        self._timeout = (5, 10)
        self._last_upload_error = None

    monkeypatch.setattr(wspr_cmd.WsprUploader, "__init__", mock_init)
    monkeypatch.setattr(
        wspr_cmd.WsprUploader,
        "drain",
        lambda self: {"attempted": 0, "succeeded": 0, "failed": 0},
    )

    heartbeat_calls: list[dict] = []

    def mock_send(self, **kwargs):
        heartbeat_calls.append(kwargs)
        return True

    monkeypatch.setattr(wspr_cmd.WsprUploader, "send_heartbeat", mock_send)

    args = Namespace(
        upload=True,
        heartbeat=True,
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
    assert len(heartbeat_calls) == 1

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data.get("heartbeat_sent") is True
