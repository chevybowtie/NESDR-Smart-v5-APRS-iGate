"""Tests for WSPR diagnostics upconverter detection heuristics."""

from neo_wspr.wspr.diagnostics import detect_upconverter_hint


def test_detect_upconverter_hint_from_spots():
    """Test upconverter detection with frequency offset."""
    # Construct spots with a median observed frequency ~14_200_000
    spots = [
        {"freq_hz": 14_200_100.0},
        {"freq_hz": 14_200_000.0},
        {"freq_hz": 14_199_900.0},
    ]
    hint = detect_upconverter_hint(spots)
    # Observed median is ~14_200_000; nearest nominal 14_080_000 => diff ~120k
    assert hint["recommended_lo_offset_hz"] is not None
    assert hint["confidence"] > 0.0


def test_upconverter_hint_empty_spots():
    """Empty/None spots should return zero confidence."""
    result = detect_upconverter_hint(None)
    assert result["confidence"] == 0.0
    assert result["recommended_lo_offset_hz"] is None

    result = detect_upconverter_hint([])
    assert result["confidence"] == 0.0
    assert result["recommended_lo_offset_hz"] is None


def test_upconverter_hint_no_offset():
    """Spots at nominal frequency should have low confidence and no recommendation."""
    spots = [
        {"freq_hz": 14080000, "snr_db": -12},
        {"freq_hz": 14080100, "snr_db": -10},
        {"freq_hz": 14079950, "snr_db": -15},
    ]
    result = detect_upconverter_hint(spots)
    assert result["confidence"] == 0.0
    assert result["recommended_lo_offset_hz"] is None
    assert result["median_freq_hz"] == 14080000


def test_upconverter_hint_large_offset():
    """Large frequency offset should trigger recommendation with confidence."""
    spots = [
        {"freq_hz": 14130000, "snr_db": -12},
        {"freq_hz": 14130100, "snr_db": -10},
        {"freq_hz": 14129950, "snr_db": -15},
    ]
    result = detect_upconverter_hint(spots)
    # Median is ~14130000, offset from 14080000 is 50000 Hz (threshold)
    assert result["confidence"] > 0.0
    assert result["recommended_lo_offset_hz"] is not None
    # Recommended offset should be ~-50000 (negate the observed offset)
    assert result["recommended_lo_offset_hz"] < 0


def test_upconverter_hint_snr_low_boosts_confidence():
    """Consistently low SNR should add to confidence score (upconverter may affect noise floor)."""
    spots = [
        {"freq_hz": 14130000, "snr_db": -28},
        {"freq_hz": 14130100, "snr_db": -30},
        {"freq_hz": 14129950, "snr_db": -27},
    ]
    result = detect_upconverter_hint(spots)
    # Should still flag the freq offset, and SNR heuristic adds confidence
    assert result["confidence"] > 0.0
    assert result["mean_snr_db"] < -25
    # Confidence should include SNR component
    assert result["confidence"] >= 0.2


def test_upconverter_hint_snr_high_boosts_confidence():
    """Unusually high SNR may indicate LNA in upconverter."""
    spots = [
        {"freq_hz": 14130000, "snr_db": 5},
        {"freq_hz": 14130100, "snr_db": 3},
        {"freq_hz": 14129950, "snr_db": 6},
    ]
    result = detect_upconverter_hint(spots)
    assert result["confidence"] > 0.0
    assert result["mean_snr_db"] > 0


def test_upconverter_hint_missing_snr():
    """Spots without SNR data should still compute frequency heuristics."""
    spots = [
        {"freq_hz": 14130000},
        {"freq_hz": 14130100},
        {"freq_hz": 14129950},
    ]
    result = detect_upconverter_hint(spots)
    assert result["median_freq_hz"] == 14130000
    assert result["mean_snr_db"] is None


def test_upconverter_hint_different_bands():
    """Heuristic should match against multiple nominal bands."""
    # Test 40m band
    spots_40m = [
        {"freq_hz": 7090000, "snr_db": -12},
        {"freq_hz": 7090100, "snr_db": -10},
    ]
    result = detect_upconverter_hint(spots_40m)
    assert result["nominal_center_hz"] == 7_040_000
    assert result["freq_offset_hz"] == 50050  # median of 7090000, 7090100

    # Test 10m band
    spots_10m = [
        {"freq_hz": 28130000, "snr_db": -12},
        {"freq_hz": 28130100, "snr_db": -10},
    ]
    result = detect_upconverter_hint(spots_10m)
    assert result["nominal_center_hz"] == 28_080_000
    assert result["freq_offset_hz"] == 50050


def test_upconverter_hint_malformed_freq():
    """Malformed freq_hz values should be skipped gracefully."""
    spots = [
        {"freq_hz": 14080000, "snr_db": -12},
        {"freq_hz": "invalid", "snr_db": -10},  # Should be skipped
        {"freq_hz": 14080100, "snr_db": -15},
    ]
    result = detect_upconverter_hint(spots)
    # Should compute with the two valid spots
    assert result["median_freq_hz"] == 14080050


def test_upconverter_hint_single_spot():
    """Single spot should be processable."""
    spots = [{"freq_hz": 14130000, "snr_db": -12}]
    result = detect_upconverter_hint(spots)
    assert result["median_freq_hz"] == 14130000
    assert result["mean_snr_db"] == -12.0
