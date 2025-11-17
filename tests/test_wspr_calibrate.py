import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import tempfile

from neo_rx.wspr.calibrate import (
    compute_ppm_from_offset,
    apply_ppm_to_radio,
    persist_ppm_to_config,
    estimate_offset_from_spots,
    load_spots_from_jsonl,
)


class TestComputePpmFromOffset:
    def test_positive_offset(self):
        ppm = compute_ppm_from_offset(100_000_000, 1000)
        assert ppm == 10.0

    def test_negative_offset(self):
        ppm = compute_ppm_from_offset(100_000_000, -500)
        assert ppm == -5.0

    def test_zero_freq_raises(self):
        with pytest.raises(ValueError, match="freq_hz must be non-zero"):
            compute_ppm_from_offset(0, 100)


class TestApplyPpmToRadio:
    @patch("rtlsdr.RtlSdr")
    def test_successful_application(self, mock_rtlsdr_cls):
        mock_sdr = MagicMock()
        mock_rtlsdr_cls.return_value = mock_sdr
        mock_rtlsdr_cls.get_device_count.return_value = 1

        apply_ppm_to_radio(15.7)

        mock_rtlsdr_cls.get_device_count.assert_called_once()
        mock_rtlsdr_cls.assert_called_once()
        mock_sdr.set_ppm_offset.assert_called_once_with(16)  # rounded
        mock_sdr.close.assert_called_once()

    @patch("rtlsdr.RtlSdr")
    def test_no_devices_found(self, mock_rtlsdr_cls):
        mock_rtlsdr_cls.get_device_count.return_value = 0

        with pytest.raises(RuntimeError, match="No RTL-SDR devices found"):
            apply_ppm_to_radio(10.0)

    def test_import_error(self):
        import builtins
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == "rtlsdr":
                raise ImportError("No module")
            return original_import(name, *args, **kwargs)
        
        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(RuntimeError, match="RTL-SDR driver unavailable"):
                apply_ppm_to_radio(10.0)

    @patch("rtlsdr.RtlSdr")
    def test_device_error(self, mock_rtlsdr_cls):
        mock_rtlsdr_cls.get_device_count.side_effect = Exception("USB error")

        with pytest.raises(RuntimeError, match="RTL-SDR ppm application failed"):
            apply_ppm_to_radio(10.0)


class TestPersistPpmToConfig:
    @patch("neo_rx.config", create=True)
    def test_successful_persist(self, mock_config):
        mock_cfg = MagicMock()
        mock_config.load_config.return_value = mock_cfg
        mock_config.resolve_config_path.return_value = Path("/fake/config.toml")
        mock_config.save_config = MagicMock()

        persist_ppm_to_config(12.3)

        assert mock_cfg.ppm_correction == 12
        mock_config.save_config.assert_called_once_with(mock_cfg, None)


class TestEstimateOffsetFromSpots:
    def test_with_expected_freq(self):
        spots = [
            {"freq_hz": 14_097_000, "snr_db": 10},
            {"freq_hz": 14_097_100, "snr_db": 12},
        ]
        result = estimate_offset_from_spots(spots, expected_freq_hz=14_097_050)
        assert result["median_observed_freq_hz"] == 14_097_050
        assert result["offset_hz"] == 0
        assert result["ppm"] == 0
        assert result["median_snr_db"] == 11
        assert result["count"] == 2

    def test_without_expected_freq(self):
        spots = [{"freq_hz": 14_097_000}]
        result = estimate_offset_from_spots(spots)
        assert result["offset_hz"] == 0
        assert result["ppm"] == 0

    def test_no_freqs_raises(self):
        with pytest.raises(ValueError, match="No frequency observations"):
            estimate_offset_from_spots([])

    def test_skips_invalid_freq(self):
        spots = [{"freq_hz": None}, {"freq_hz": 14_097_000}]
        result = estimate_offset_from_spots(spots)
        assert result["count"] == 1


class TestLoadSpotsFromJsonl:
    def test_load_valid_file(self):
        data = [
            {"freq_hz": 14097000, "snr_db": 10},
            {"freq_hz": 14097100, "snr_db": 12},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for spot in data:
                json.dump(spot, f)
                f.write("\n")
            path = Path(f.name)

        try:
            spots = load_spots_from_jsonl(path)
            assert len(spots) == 2
            assert spots[0]["freq_hz"] == 14097000
        finally:
            path.unlink()

    def test_file_not_found(self):
        spots = load_spots_from_jsonl(Path("/nonexistent.jsonl"))
        assert spots == []


from neo_rx.wspr.calibrate import estimate_offset_from_spots, compute_ppm_from_offset


def test_compute_ppm_from_offset_basic():
    # 1 kHz offset at 14.08 MHz -> ~0.0710 ppm
    freq = 14_080_000.0
    offset = 1000.0
    ppm = compute_ppm_from_offset(freq, offset)
    assert abs(ppm - (1000.0 / 14_080_000.0 * 1_000_000.0)) < 1e-6


def test_estimate_offset_from_spots_with_expected():
    spots = [
        {"freq_hz": 14_080_020.0, "snr_db": 10},
        {"freq_hz": 14_080_010.0, "snr_db": 12},
        {"freq_hz": 14_080_050.0, "snr_db": 8},
    ]
    expected = 14_080_000.0
    res = estimate_offset_from_spots(spots, expected)
    # median of freqs is 14080020.0
    assert res["count"] == 3
    assert res["median_observed_freq_hz"] == 14_080_020.0
    assert res["offset_hz"] == 20.0
    assert abs(res["ppm"] - compute_ppm_from_offset(expected, 20.0)) < 1e-9
